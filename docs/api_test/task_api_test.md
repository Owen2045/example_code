
# 建立謄本任務 --> OK
1. 強制，非強制調閱
2. 高優先覆蓋低優先
3. mark_only測試



```py
lbkey_data = [  
                # {'lbkey': 'F_01_0419_0529-0000', 'o_regno_str':'0003,0009', 'r_regno_str':'0004000,0004000', 'priority': 60},
                {'lbkey': 'B_02_0308_0028-0810', 'r_regno_str':'0068000,0270000', 'priority': 87},
                {'lbkey': 'B_02_0308_0028-1103', 'o_regno_str':'6400,7000', 'is_mark_only':True},#'priority': 80
                {'lbkey': 'B_02_9309_0036-0010', 'o_regno_str':'5000', 'priority':50, 'system':2},
                {'lbkey': 'A_11_0132_0572-0000', 'o_regno_str':'5000', 'priority':50},
                # {'lbkey': 'F_01_0307_0322-0006', 'o_regno_str':'0081,0010', 'r_regno_str':'0008000,0640000', 'priority': 80},
            ]

url = 'http://127.0.0.1:8080/common/tp/input_task/'
data = {
    'task_data': lbkey_data,
    'forcibly': 1, 
    'debug': False,  # True False
}
requests.post(url, json=data, headers=headers)
```
# 匯入謄本log

```py
datas = [
    {
    'lbkey': 'B_04_0759_00487-000', 
    'query_system': 3, 
    'owners': {}, 
    'rights': {}, 
    'rules': 1, 
    'state': 0, 
    'transcript': {}, 
    'task_id': 5,
    'is_fast': False,
    'query_time': '2022-07-05 10:10:10'
    },
    {
    'lbkey': 'B_11_0132_0572-0000', 
    'query_system': 3, 
    'owners': {}, 
    'rights': {}, 
    'rules': 1, 
    'state': 0, 
    'transcript': {}, 
    'is_fast':False,
    'task_id': 17,
    'query_time': '2022-07-05 10:10:10'
    }
]
url = 'http://127.0.0.1:8080/common/tp/feedback/'
requests.post(url, json=datas, headers=headers)
```



# lbor建任務 --> OK

```py
datas = [
    {
    'lbkey_list': ['B_02_0308_0028-0818', 'F_01_0431_0086-0000', 'G_11_0132_0572-0000', 'B_02_0308_0028-1020', 'B_02_0308_9028-1020'], 
    'forcibly': True,
    'priority': 60,
    'rules': 2
    },
    {
    'lbkey_list': ['G_11_0132_0572-0000'], 
    'forcibly': True,
    'priority': 70,
    'rules': 1
    }
]
url = 'http://127.0.0.1:8080/common/lbor/input_task/'
requests.post(url, json=datas, headers=headers)
```


# lbor產製任務
1. * 放左或放右表示不限制最大數或最小數
```py
Cdatas = {
    'CAR': 'A_02',
    'development': '', 
    'use_zone':'道路',
    'time_start': '2021-10-14', 
    'time_end': '2021-10-18', 
    'owners_num': '0,*', 
    'rights_num': '0,*', 
    'building_num': '0,*', 
    'vp_price': '1,300',
    'o_private': '0,9',
    'o_rental': '0,3',
    'o_goverment': '0,0',
    'o_company': '0,1', 
    'o_finance': None,

    'r_private': '0,9',
    'r_rental': '0,0',
    'r_goverment': '0,0',
    'r_company': '0,0', 
    'r_finance': None,

    'limit': 20
}
url = 'http://127.0.0.1:8080/common/lbor/generate_task/'
requests.post(url, data=Cdatas, headers=headers)
```