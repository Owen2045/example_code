# lbor V3 謄本 commands 功能介紹

## [v2謄本log匯入](/common/management/commands/update_from_104_tp.py)

> 從v2匯入log

python manage.py update_from_104_tp --lb L

--lb -> L or B 

## [謄本解析](/common/management/commands/parser_tp.py)

> 解析log

python manage.py parser_tp -t L -n 10 -b 2 -i 1 3 4 5

-t -> L or B

-n -> 一次取多少任務

-b -> 一個批次多少任務

-i -> 指定id解析log
