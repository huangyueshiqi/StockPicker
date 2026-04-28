import pandas as pd
import numpy as np
import xgboost as xgb
import shap
import matplotlib.pyplot as plt
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, roc_auc_score,recall_score,accuracy_score
import warnings

warnings.filterwarnings('ignore')

"""
xgboost全量训练，目标是覆盖尽可能多的正样本，使用shap分析，提取累计覆盖度达到80%的特征，相当于进行特征选择
"""

def select_features_by_shap_coverage(importance_df, coverage=0.8):
    importance_df = importance_df.copy()
    total = float(importance_df['shap_importance'].sum())
    importance_df['importance_ratio'] = importance_df['shap_importance'] / total
    importance_df['cumulative_ratio'] = importance_df['importance_ratio'].cumsum()
    cut_idx = int(importance_df['cumulative_ratio'].ge(coverage).idxmax())
    selected = importance_df.iloc[: cut_idx + 1].copy()
    return selected, importance_df

def train_and_explain(df, feature_cols, target_col='label', train_full=False, shap_coverage=0.8):
    """
    训练 XGBoost 模型，并使用 SHAP 进行特征归因分析
    """
    if train_full:
        X_train, y_train = df[feature_cols], df[target_col]
        X_eval, y_eval = None, None
        print(f"\n使用全量数据训练: {X_train.shape}")
    else:
        print("\n划分训练集和测试集 (按时间序列前80%作为训练集)...")
        split_idx = int(len(df) * 0.8)
        train_df = df.iloc[:split_idx]
        test_df = df.iloc[split_idx:]
        X_train, y_train = train_df[feature_cols], train_df[target_col]
        X_eval, y_eval = test_df[feature_cols], test_df[target_col]
        print(f"训练集大小: {X_train.shape}, 测试集大小: {X_eval.shape}")

    # 2. 模型训练
    print("\n开始训练 XGBoost 模型...")
    # XGBoost 参数设置 (二分类任务)
    model = xgb.XGBClassifier(
        n_estimators=100,  # 树的数量
        max_depth=5,  # 树的最大深度
        learning_rate=0.05,  # 学习率
        subsample=0.8,  # 样本采样率，防止过拟合
        colsample_bytree=0.8,  # 特征采样率
        random_state=42,
        n_jobs=-1,
        eval_metric='logloss'  # 评估指标
    )

    fit_kwargs = {'verbose': False}
    if X_eval is not None and y_eval is not None:
        fit_kwargs['eval_set'] = [(X_eval, y_eval)]
    model.fit(X_train, y_train, **fit_kwargs)

    # 3. 模型评估
    if X_eval is not None and y_eval is not None:
        preds = model.predict(X_eval)
        preds_proba = model.predict_proba(X_eval)[:, 1]
        print("\n=== 模型在测试集上的表现 ===")
        print(classification_report(y_eval, preds))
        print(f"ROC-AUC Score: {roc_auc_score(y_eval, preds_proba):.4f}")
        print(f"Accuracy Score:{accuracy_score(y_eval,preds):.4f}")
        print(f"Recall Score(Positive class):{recall_score(y_eval,preds):.4f}")
    else:
        preds = model.predict(X_train)
        preds_proba = model.predict_proba(X_train)[:, 1]
        print("\n=== 模型在训练集上的表现（仅作参考） ===")
        print(classification_report(y_train, preds))
        print(f"ROC-AUC Score: {roc_auc_score(y_train, preds_proba):.4f}")
        print(f"Accuracy Score:{accuracy_score(y_train, preds):.4f}")
        print(f"Recall Score(Positive class):{recall_score(y_train, preds):.4f}")

    # 4. SHAP 分析与特征重要性提取
    print("\n开始计算 SHAP 值 (可能需要几秒钟)...")
    # 对于树模型，推荐使用 TreeExplainer
    explainer = shap.TreeExplainer(model)

    X_shap = X_train if train_full else X_eval
    try:
        shap_values = explainer(X_shap, check_additivity=False)
    except TypeError:
        shap_values = explainer(X_shap)

    print("提取特征重要性排名...")
    # 计算每个特征在所有样本上的平均绝对 SHAP 值
    # shap_values.values 包含每个样本每个特征的 SHAP 值
    mean_abs_shap = np.abs(shap_values.values).mean(axis=0)

    importance_df = pd.DataFrame({
        'feature': feature_cols,
        'shap_importance': mean_abs_shap
    })

    # 降序排列
    importance_df = importance_df.sort_values(by='shap_importance', ascending=False).reset_index(drop=True)

    print("\n=== Top 10 最重要的特征 ===")
    print(importance_df.head(10))

    # 5. 保存特征重要性到 CSV
    output_csv = "feature_shap_importance.csv"
    importance_df.to_csv(output_csv, index=False)
    print(f"\n特征重要性已保存至: {output_csv}")

    selected_df, importance_with_ratio = select_features_by_shap_coverage(importance_df, coverage=shap_coverage)
    selected_path = "selected_features_80pct.csv"
    selected_df.to_csv(selected_path, index=False)
    print(f"累计重要性覆盖 {int(shap_coverage * 100)}% 的特征已保存至: {selected_path} (共 {len(selected_df)} 列)")

    # 6. 绘制并保存 SHAP 摘要图 (Summary Plot)
    print("生成并保存 SHAP 摘要图...")
    plt.figure(figsize=(10, 8))
    # plot_type="dot" 是标准的蜜蜂图，显示正负影响
    shap.summary_plot(shap_values, X_shap, max_display=20, show=False)
    plt.tight_layout()
    plt.savefig("shap_summary_plot.png", dpi=300)
    plt.close()
    print("SHAP摘要图已保存至: shap_summary_plot.png")


if __name__ == "__main__":
    df=pd.read_csv("df_value.csv")
    exclude_cols = ['fund', 'instrument', 'datetime', 'label']
    feature_cols = [c for c in df.columns if c not in set(exclude_cols)]

    # 查看生成的数据结构
    print("\n数据预览 (前5行):")
    # 打印基础维度和前5个特征
    cols_to_show = ['fund', 'instrument', 'datetime', 'label'] + feature_cols[:5]
    print(df[cols_to_show].head())

    # 2. 训练并进行 SHAP 归因
    train_and_explain(df, feature_cols, target_col='label',train_full=True, shap_coverage=0.8)





