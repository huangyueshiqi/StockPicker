import requests
import json
import time

start_time=time.time()
url = "http://172.21.16.9/ms-tnpb4z5j/v1/chat/completions"
# url="http://172.21.16.9/ms-r6rcvnnp/v1/chat/completions"
headers = {
    "Content-Type": "application/json"
}

payload = {
    "model": "Kimi-K2.6",
    # "model": "deepseek-v3",
    "messages": [
        {
            "role": "system",
            "content": "你是一个助手，请按照用户要求回答问题."
        },
        {
            "role": "user",
            "content": """
            天空是什么颜色
            """
        }
    ],
    "temperature": 0.7,
    "max_tokens": 1000
}

response = requests.post(url, headers=headers, json=payload, timeout=60)
response.raise_for_status()

result = response.json()
print("Response:", json.dumps(result, indent=2, ensure_ascii=False))
print(f"time cost:{time.time()-start_time}")



# 回测区间：2015-01-01到2025-12-31。寻找pvt_ashareenergyindexadj小于2878390，ma_120d_ashareintensitytrendadj大于64，ma_120d_ashareintensitytrendadj小于65这三个条件都满足的股票，每60个交易日调仓，等权持仓，选前20只
# 回测区间：2015-01-01到2025-12-31。寻找pvt_ashareenergyindexadj大于2878390，amount_m_ashareyield大于5448446，tapi_6d_asharetechindicators大于236246这三个条件都满足的股票，每60个交易日调仓，等权持仓，选前20只

#
# curl --location --request POST 'http://172.21.16.9/ms-tnpb4z5j/v1/chat/completions' \
# --header 'Content-Type: application/json' \
# --data-raw '{
#   "model": "Kimi-K2.6",
#   "chat_template_kwargs": {"thinking": false},
#   "messages": [
#     {
#       "role": "user",
#       "content": "你是谁"
#     }
#   ]
# }'  model参数可以是空字符串或者Kimi-K2.6，现在这个vllm版本不能填其他的了会报模型名称不存在。讲解一下