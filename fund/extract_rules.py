import os
import sys
import re
import json
import logging
from typing import List, Dict, Optional, Any
import argparse
import pandas as pd
import numpy as np
from sklearn.tree import DecisionTreeClassifier, export_text, plot_tree
from imodels import RuleFitClassifier
import matplotlib.pyplot as plt

from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('LLMRuleAnalyzer')


"""
使用shap特征选择得到的特征重新训练一个最大深度为3的决策树
遍历树的路径，筛选出一条选股大概率是正样本(>0.6)且正样本数量占总样本比例较高（>5%）的路径
"""


def get_lineage(tree, feature_names):
    """
    遍历决策树，提取从根节点到每个叶子节点的完整规则路径。
    返回一个字典：{leaf_node_id: [(feature, operator, threshold), ...]}
    """
    left = tree.tree_.children_left
    right = tree.tree_.children_right
    threshold = tree.tree_.threshold
    features = [feature_names[i] if i != -2 else "undefined!" for i in tree.tree_.feature]

    def recurse(left, right, child, lineage=None):
        if lineage is None:
            lineage = [child]
        if child in left:
            parent = np.where(left == child)[0].item()
            split = 'L'
        else:
            parent = np.where(right == child)[0].item()
            split = 'R'

        # 记录：如果是左子树，说明满足 <= 阈值；如果是右子树，说明满足 > 阈值
        op = "<=" if split == 'L' else ">"
        val = threshold[parent]
        feat = features[parent]

        rule = (feat, op, val)

        lineage.append(rule)

        if parent == 0:
            lineage.reverse()
            return lineage
        else:
            return recurse(left, right, parent, lineage)

    # 获取所有的叶子节点ID
    leaves = np.where(left == -1)[0]

    paths = {}
    for leaf in leaves:
        if leaf==0:
            #特殊情况，如果根节点就是叶子节点（树只有深度为0）
            paths[leaf]=[]
            continue
        path = recurse(left, right, leaf)
        # 第一个是根节点0，最后一个是叶子节点自身编号，中间构建的rule tuple
        #提取 rule列表
        rules_only=[item for item in path if isinstance(item,tuple)]
        paths[leaf] = rules_only
    return paths

def extract_rules_from_top_features(df, top_features_file='selected_features_80pct.csv', target_col='label',
                                    max_depth=3):
    """
    使用单棵浅层决策树，从选出的核心特征中提取人类可读的 If-Else 选股规则。
    参数:
    - df: 包含特征和 label 的 DataFrame (例如从 build_df_for_xgb 出来的 df)
    - top_features_file: SHAP 挑选出的核心特征 CSV 文件路径
    - max_depth: 决策树最大深度，建议 3-4，太深规则会过于复杂
    """


    print(f"1. 加载核心特征列表: {top_features_file}")
    top_features_df = pd.read_csv(top_features_file)
    # 提取特征名列表
    core_features = top_features_df['feature'].tolist()
    print(f"   成功加载 {len(core_features)} 个核心特征。")

    # 2. 准备数据
    print(f"\n2. 准备决策树训练数据 (仅使用核心特征)...")
    # 确保所选特征在 df 中存在
    valid_features = [f for f in core_features if f in df.columns]
    X = df[valid_features]
    y = df[target_col]
    # 填充可能存在的缺失值 (决策树不支持 NaN，用中位数填充较为稳妥)
    X = X.fillna(X.median())
    # 3. 训练浅层决策树
    print(f"\n3. 训练浅层决策树 (最大深度={max_depth})...")
    # 设置 class_weight='balanced' 是因为正负样本比例通常是 1:10
    tree_clf = DecisionTreeClassifier(max_depth=max_depth, class_weight='balanced', random_state=42)
    tree_clf.fit(X, y)
    # 4. 打印纯文本的 If-Else 规则
    print("\n=======================================================")
    print(" 提取的选股规则 (If-Else 形式) ")
    print("说明: class: 1 代表基金可能买入(正样本)，class: 0 代表不买(负样本)")
    print("=======================================================\n")
    tree_rules = export_text(tree_clf, feature_names=valid_features)
    print(tree_rules)
    # 5. 寻找高胜率的“买入规则” (叶子节点分析)
    print("\n--- 高胜率买入路径分析 ---")
    pandas_rules=analyze_leaf_nodes(tree_clf, valid_features, X, y)

    # 6. 可视化并保存决策树结构图
    print("\n4. 正在生成决策树可视化图 (decision_tree_rules.png)...")
    plt.figure(figsize=(20, 10))
    plot_tree(
        tree_clf,
        feature_names=valid_features,
        class_names=['Not Buy (0)', 'Buy (1)'],
        filled=True,
        rounded=True,
        proportion=True,
        fontsize=10
    )
    plt.savefig('decision_tree_rules.png', dpi=300, bbox_inches='tight')
    plt.close()
    print("   保存成功！可以通过查看该图片直观地了解各个阈值划分。")
    return pandas_rules


def analyze_leaf_nodes(tree_clf, feature_names, X, y):
    """
    分析决策树的叶子节点，找出预测为正类(买入)且纯度较高(胜率高)的规则路径，
    并直接输出可用于 Pandas/回测 的 Python 代码。
    """


    tree_ = tree_clf.tree_
    paths = get_lineage(tree_clf, feature_names)

    high_prob_rules = []
    pandas_rules=[]
    desc_df=pd.read_csv("/home/quant/zc/backtrader/QuantStockPicker/documents/财务量价字段表.csv")

    # 遍历所有叶子节点
    for leaf_id, path in paths.items():
        # 获取该叶子节点的样本分布 [负样本权重和, 正样本权重和]
        value = tree_.value[leaf_id][0]
        # 计算预测为正类 (买入) 的概率
        buy_prob = value[1] / (value[0] + value[1])
        # 样本数量
        samples = tree_.n_node_samples[leaf_id]

        # 定义高潜规则：买入概率 > 60% 且 覆盖样本数 > 总样本的 5%
        if buy_prob > 0.6 and samples > len(X) * 0.05:
            # 拼接 Pandas 的查询条件
            if not path:
                continue
            conditions = []
            for feat, op, val in path:
                # 例如： (df['feature_A'] > 3.5)
                parts=feat.rsplit('_',1)
                field_name=parts[0]
                # 去除 cor_ 或 adj_ 前缀
                field_name = re.sub(r'^(cor|adj)_', '', field_name, count=1)
                table_name=parts[1]
                mask=(desc_df['field_name']==field_name)&(desc_df['table_name']==table_name)

                filtered = desc_df[mask]
                if len(filtered) > 0:
                    desc_value = filtered['注释'].values[0]
                else:
                    desc_value = "未知"  # 或者设置默认值
                    print(f"警告: 特征 '{feat}' 在描述文件中未找到匹配项")

                conditions.append(f"('{feat}' {op} {val:.4f},'{feat}':'{desc_value}')")

            pandas_rule = " & ".join(conditions)

            high_prob_rules.append({
                'node_id': leaf_id,
                'buy_prob': buy_prob,
                'samples': samples,
                'rule_code': pandas_rule
            })

            print(f"⭐ 发现高潜选股节点 (节点ID: {leaf_id}):")
            print(f"   - 覆盖样本数: {samples} (占总样本 {samples / len(X) * 100:.1f}%)")
            print(f"   - 预测买入胜率 (加权): {buy_prob * 100:.1f}%")
            print(f"   - 实际命中正样本数: {int(value[1])}")
            print(f"   - 【回测提取代码】:\n     selected_stocks = df[{pandas_rule}]\n")
            pandas_rules.append(pandas_rule)
    return pandas_rules


def extract_rules_with_rulefit(df, top_features_file='selected_features_80pct.csv', target_col='label', max_rules=20):
    """
    使用 RuleFit 算法从核心特征中提取带有权重 (系数) 的选股规则。
    RuleFit 结合了树模型的非线性特征组合和 Lasso 回归的特征选择能力，
    能自动剔除冗余规则，留下最具代表性的高胜率路径。
    """
    print(f"\n=======================================================")
    print(f"启动 RuleFit 算法规则提取 (最大规则数: {max_rules}) ")
    print(f"=======================================================\n")

    # 1. 加载核心特征
    top_features_df = pd.read_csv(top_features_file)
    core_features = top_features_df['feature'].tolist()
    print(f"1. 成功加载 {len(core_features)} 个核心特征。")

    # 2. 准备数据
    valid_features = [f for f in core_features if f in df.columns]
    X = df[valid_features].fillna(df[valid_features].median())
    y = df[target_col]

    print(f"2. 准备训练数据完成，特征维度: {X.shape}")

    # 3. 训练 RuleFit
    print(f"3. 正在训练 RuleFit 模型，请稍候...")
    rf = RuleFitClassifier(max_rules=max_rules, random_state=42)

    # 捕获并忽略内部的 Lasso 警告
    rf.fit(X, y, feature_names=valid_features)

    # 4. 提取并过滤规则
    df_rules = rf._get_rules()

    # 我们只关心预测正类（买入）的规则，即 coef > 0
    buy_rules = df_rules[(df_rules['type'] == 'rule') & (df_rules['coef'] > 0)].copy()

    if buy_rules.empty:
        print("\n⚠️ RuleFit 未能找到具有正向权重的买入规则，建议增加 max_rules 或检查数据。")
        return

    # 按重要性（或系数大小）排序
    buy_rules = buy_rules.sort_values(by='coef', ascending=False)

    print("\n---  RuleFit 提取的高价值买入规则 ---")

    final_pandas_rules = []

    for i, row in buy_rules.iterrows():
        rule_str = row['rule']
        coef = row['coef']
        importance = row['importance']
        support = row['support']  # 规则覆盖的样本比例

        # 将 RuleFit 的规则字符串 (例如: feature_A <= 4.2 and feature_B > 8.8)
        # 转换为 Pandas 查询格式: (df['feature_A'] <= 4.2) & (df['feature_B'] > 8.8)
        conditions = rule_str.split(' and ')
        pd_conds = []
        for cond in conditions:
            # 解析特征、操作符和值
            parts = cond.split(' ')
            if len(parts) == 3:
                feat, op, val = parts[0], parts[1], parts[2]
                pd_conds.append(f"(df['{feat}'] {op} {val})")

        pandas_rule = " & ".join(pd_conds)
        final_pandas_rules.append({'code': pandas_rule, 'coef': coef})

        print(f"⭐ 规则 {len(final_pandas_rules)}:")
        print(f"   - 逻辑: {rule_str}")
        print(f"   - 权重 (Coef): +{coef:.4f} (正向打分越大，买入概率越高)")
        print(f"   - 覆盖率: {support * 100:.1f}%")
        print(f"   - 【回测代码】: df[{pandas_rule}]\n")

    for i, rule in enumerate(final_pandas_rules):
        print(f"    # 规则 {i + 1} (权重: +{rule['coef']:.4f})")
        print(f"    mask_{i + 1} = {rule['code']}")
        print(f"    df.loc[mask_{i + 1}, 'rulefit_score'] += {rule['coef']:.4f}\n")





def read_csv_fields(file_paths):
    """
    读取 CSV 字段文件，生成候选字段集合字符串
    """
    all_fields = []
    for file_path in file_paths:
        if not os.path.exists(file_path):
            continue

        df=pd.read_csv(file_path)
        if "中文名" in df.columns:
            df.rename(columns={'中文名':'注释'},inplace=True)
        for i,field_info in df.iterrows():
            all_fields.append(field_info)
    all_fields=pd.DataFrame(all_fields)
    all_fields.to_csv(f"财务量价字段表.csv",encoding='utf-8-sig',index=False)
    return all_fields




class RuleItem(BaseModel):
    expression: str = Field(..., description="一条规则表达式（可包含AND/OR）")
    explanation: str = Field(..., description="用金融语言解释这条规则在表达什么")


class StrategyAnalysisSchema(BaseModel):
    one_liner: str = Field(..., description="一句话策略描述")
    rule_interpretation: List[RuleItem] = Field(..., description="规则逐条解释")
    robust_suggestions: List[str] = Field(..., description="稳健化建议")
    risk_points: List[str] = Field(..., description="风险点")
    assumptions: List[str] = Field(..., description="因输入缺失而做出的假设或需要进一步确认的信息")


LLM_RULE_ANALYSIS_PROMPT = """
你是量化研究员助手。输入是一段“决策树提取出的买入规则 + 字段含义/公式/单位”的文本，以及已知的部分回测信息。
你的任务是将其转写为严格 JSON，帮助研究员形成可解释、可落地且可审阅的交易策略描述。

要求：
1) 只基于输入文本推理，不要编造字段含义或数据来源。
2) one_liner 输出示例风格（仅示例，不要照抄数字）：回测区间：2021-01-01到2025-12-31。寻找低市盈率(PE_TTM)且高ROE的股票，每60个交易日调仓，等权持仓，选前20只。
3） 请根据输入信息自行推理选择最合适的调仓周期和选股数量。 调仓周期：30、60、120交易日，选股数量：前5、10、20、30只
4) rule_interpretation 中请尽量把每个条件解释为“趋势/动量/成交活跃/风险偏好/流动性”等金融语言，并指出该条件属于择时过滤还是偏向选股特征。。

输入规则文本：
{user_input}

已知回测信息：
 - 开始日期：{start_date}
 - 结束日期：{end_date}

{format_instructions}
"""

# 2) 若缺少回测区间、调仓周期、选股数量、权重方式等信息，不要硬猜具体数值；可以在 one_liner 中用“未知/待定”，并在 assumptions 中列出需要补充的信息或你采取的默认假设。
class LLMRuleAnalyzer:
    def __init__(
        self,
        model: str = "gpt-4o",
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        temperature: float = 0.2,
        timeout: int = 240,
    ):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.base_url = base_url or os.getenv("OPENAI_BASE_URL")

        self.llm = ChatOpenAI(
            model=model,
            base_url=self.base_url,
            api_key=self.api_key,
            timeout=timeout,
            temperature=temperature,
        )

    def analyze(self, user_input: str, start_date,end_date,output_file: str) -> Optional[Dict[str, Any]]:
        parser = JsonOutputParser(pydantic_object=StrategyAnalysisSchema)
        prompt = ChatPromptTemplate.from_template(
            template=LLM_RULE_ANALYSIS_PROMPT,
            partial_variables={"format_instructions": parser.get_format_instructions()},
        )
        chain = prompt | self.llm | parser

        try:
            result = chain.invoke({"user_input": user_input,'start_date':start_date,'end_date':end_date})
            os.makedirs(os.path.dirname(os.path.abspath(output_file)), exist_ok=True)
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            print(result)
            logger.info(f"策略分析结果已保存至: {output_file}")
            return result
        except Exception as e:
            logger.error(f"生成策略分析失败: {e}")
            return None



if __name__ == "__main__":
    # 这里构造一个非常简单的假 df 用于演示脚本运行
    print("--- 启动决策树规则提取演示 ---")
    df = pd.read_csv("df_value.csv")
    start_date=df['datetime'].min()
    end_date=df['datetime'].max()
    # 运行提取
    user_inputs=extract_rules_from_top_features(df, top_features_file='selected_features_80pct.csv', target_col='label', max_depth=5)
    # read_csv_fields(['/home/quant/zc/backtrader/QuantStockPicker/documents/财务字段中英文对照表.csv','/home/quant/zc/backtrader/QuantStockPicker/documents/量价字段中英文对照表.csv'])
    # 运行 RuleFit 提取
    # extract_rules_with_rulefit(df, top_features_file='selected_features_80pct.csv', target_col='label', max_rules=10)

    # analyzer = LLMRuleAnalyzer(
    #     model="",
    #     base_url="http://172.21.16.9/ms-tnpb4z5j/v1",
    #     api_key="app-kKH20nKvnhRhRzoAZSMWhFVJ",
    #     temperature=0.4,
    # )
    analyzer = LLMRuleAnalyzer(model="deepseek-v3", base_url="http://172.21.16.9/ms-r6rcvnnp/v1",
                                     api_key="app-kKH20nKvnhRhRzoAZSMWhFVJ",temperature=0.4,)
    i=0
    for user_input in user_inputs:
        analyzer.analyze(user_input=user_input,start_date=start_date,end_date=end_date, output_file=f"analysis_{i}.json")
        i+=1



# --- 高胜率买入路径分析 ---
# ⭐ 发现高潜选股节点 (节点ID: 6):
#    - 覆盖样本数: 1628 (占总样本 20.2%)
#    - 预测买入胜率 (加权): 95.8%
#    - 实际命中正样本数: 1560 (估算)
#    - 【回测提取代码】:
#      selected_stocks = df[(df['pvt_ashareenergyindexadj'] <= 2878390.2500) & (df['ma_120d_ashareintensitytrendadj'] > 64.1205) & (df['ma_120d_ashareintensitytrendadj'] <= 64.3582)]
#
# ⭐ 发现高潜选股节点 (节点ID: 14):
#    - 覆盖样本数: 705 (占总样本 8.7%)
#    - 预测买入胜率 (加权): 69.8%
#    - 实际命中正样本数: 492 (估算)
#    - 【回测提取代码】:
#      selected_stocks = df[(df['pvt_ashareenergyindexadj'] > 2878390.2500) & (df['amount_m_ashareyield'] > 5448446.0000) & (df['tapi_6d_asharetechindicators'] > 236246.5547)]