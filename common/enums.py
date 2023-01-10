from enum import Enum, IntEnum


class StrChoiceEnum(str, Enum):

    @classmethod
    def nameList(cls):
        return list(map(lambda x: x.name, cls))

    @classmethod
    def valueList(cls):
        return list(map(lambda x: x.value, cls))

    @classmethod
    def choices(cls):
        return tuple(lambda x: (x.name, x.value), cls)

    @classmethod
    def dictionary(cls):
        return dict(map(lambda x: x, cls.choices()))

class IntChoiceEnum(IntEnum):

    @classmethod
    def nameList(cls):
        return list(map(lambda x: x.name, cls))

    @classmethod
    def valueList(cls):
        return list(map(lambda x: x.value, cls))

    @classmethod
    def choices(cls):
        return tuple(lambda x: (x.name, x.value), cls)

    @classmethod
    def dictionary(cls):
        return dict(map(lambda x: x, cls.choices()))

# 驗證類別
class IsvalidTypeEnum(IntEnum):
    # 有效
    VALID = 20
    # 有效 登序有問題
    VALID_REGNO = 21
    # 有效 待查詢(不完全查 或新地建號)
    VALID_NEED_QUERY = 22
    # 有效 無效轉換
    VALID_INVALID_CHANGE = 23
    # 有效 公設
    VALID_PUBLIC_FACILITY = 24

    # 無效
    INVALID = 40
    # 無效 已驗證
    CHECK_INVALID = 41
    # 無效 登序有問題
    INVALID_REGNO = 42
    # 無效 無所他權人
    INVALID_NOT_OR = 43

    @classmethod
    def choices(cls):
        CHOICES = (
            (cls.VALID.value, '有效'),
            (cls.VALID_REGNO.value, '有效 登序有問題'),
            (cls.VALID_NEED_QUERY.value, '有效 待查詢'),
            (cls.VALID_INVALID_CHANGE.value, '有效 無效轉換'),
            (cls.VALID_PUBLIC_FACILITY.value, '有效 公設'),
            (cls.INVALID.value, '無效'),
            (cls.CHECK_INVALID.value, '無效 已驗證'),
            (cls.INVALID_REGNO.value, '無效 登序有問題'),
            (cls.INVALID_NOT_OR.value, '無效 無所他權人'),
        )
        return CHOICES

# 設定類別
class PropertyTypeEnum(IntEnum):
    # 無
    NONETYPE = -1
    # 不詳
    UNKNOWN = 0
    # 政府機構
    GOVERMENT = 1
    # 自然人
    PRIVATE = 2
    # 公司
    COMPANY = 3
    # 租賃業者
    RENTAL = 4
    # 金融機構
    FINANCE = 5

    @classmethod
    def choices(cls):
        CHOICES = (
            (cls.NONETYPE.value, '無'),
            (cls.UNKNOWN.value, '不詳'),
            (cls.GOVERMENT.value, '政府機構'),
            (cls.PRIVATE.value, '自然人'),
            (cls.COMPANY.value, '公司'),
            (cls.RENTAL.value, '租賃業者'),
            (cls.FINANCE.value, '金融機構'),
        )
        return CHOICES

# 選單類別
class MenuTypeEnum(IntEnum):
    # 無效
    INVALID = 0
    # 新增
    ADD = 1
    # 修改
    MODIFY = 2

    @classmethod
    def choices(cls):
        CHOICES = (
            (cls.INVALID.value, '無效'),
            (cls.ADD.value, '新增'),
            (cls.MODIFY.value, '修改'),
        )
        return CHOICES

# 查詢狀態類別
class TaskTypeEnum(IntEnum):
    # 待處理
    INIT = 0

    # 查詢中
    PROCESSING = 10
    # 解析中
    PARSER = 11

    # 完成
    COMPLETE = 20
    # 完成 無變動
    COMPLETE_NO_CHANGE = 21

    # 異常
    ABNORMAL = 40
    # 異常 解析
    ABNORMAL_PARSER = 41
    # 異常 重複
    ABNORMAL_REPEAT = 42
    # 異常 無縣市行政區段小段
    ABNORMAL_CAR = 43

    # 廢棄
    DISCARD = 50

    @classmethod
    def choices(cls):
        CHOICES = (
            (cls.INIT.value, '待處理'),
            (cls.PROCESSING.value, '查詢中'),
            (cls.PARSER.value, '解析中'),
            (cls.COMPLETE.value, '完成'),
            (cls.COMPLETE_NO_CHANGE.value, '完成無變動'),
            (cls.ABNORMAL.value, '異常'),
            (cls.ABNORMAL_PARSER.value, '異常解析'),
            (cls.ABNORMAL_REPEAT.value, '異常重複'),
            (cls.ABNORMAL_CAR.value, '異常無CAR'),
            (cls.DISCARD.value, '廢棄'),
        )
        return CHOICES

# 查詢模式類別
class ModeTypeEnum(IntEnum):
    # TODO 模式內容待定義
    MODE0 = 0
    MODE1 = 1
    MODE2 = 2

    @classmethod
    def choices(cls):
        CHOICES = (
            (cls.MODE0.value, '預設'),
            (cls.MODE1.value, '所他一人'),
            (cls.MODE2.value, '所他5人以上'),
        )
        return CHOICES

# 規則類別
class RuleTypeEnum(IntEnum):
    # 只查所有權
    OWNER = 0
    # 只查他項權
    RIGHT = 1
    # 只查標示部
    MARK = 2
    # 全查
    BOTH = 3
    # 部份查
    APRT = 4

    @classmethod
    def choices(cls):
        CHOICES = (
            (cls.OWNER.value, '只查所有權'),
            (cls.RIGHT.value, '只查他項權'),
            (cls.MARK.value, '只查標示部'),
            (cls.BOTH.value, '全查'),
            (cls.APRT.value, '部份查'),
        )
        return CHOICES

# 謄本選單類別
class TpMenuTypeEnum(IntEnum):
    UNKNOW = 0
    FULL = 1
    SPECIFY = 2
    MARK_ONLY = 3
    INCOMPLETE = 4

    @classmethod
    def choices(cls):
        CHOICES = (
            (cls.UNKNOW.value, '未知'),
            (cls.FULL.value, '完整'),
            (cls.SPECIFY.value, '特定'),
            (cls.MARK_ONLY.value, '標示部'),
            (cls.INCOMPLETE.value, '不完整'),
        )
        return CHOICES

# 查詢系統類別
class QuerySystemEnum(IntEnum):
    GAIAS_MOBILE = 1
    GAIAS_PC = 2
    QUANTA_MOBILE = 3
    QUANTA_PC = 4
    KANGDA_MOBILE = 5
    KANGDA_PC = 6
    SECURE = 7
    TRADE_VAN = 8
    TOOLBOX = 10
    TELEX_PDF = 11
    TELEX_PDF_DW = 12
    QUANTA_PC_ROAD = 21
    LOR_V2 = 30
    V523 = 31
    LOR_V3 = 32


    @classmethod
    def choices(cls):
        CHOICES = (
            (cls.GAIAS_MOBILE.value, '群旋手機(棄用)'),
            (cls.GAIAS_PC.value, '群旋'),
            (cls.QUANTA_MOBILE.value, '光特手機(棄用)'),
            (cls.QUANTA_PC.value, '光特'),
            (cls.KANGDA_MOBILE.value, '康大手機(棄用)'),
            (cls.KANGDA_PC.value, '康大'),
            (cls.SECURE.value, '華安'),
            (cls.TRADE_VAN.value, '關貿'),
            (cls.TOOLBOX.value, '工具箱'),
            (cls.TELEX_PDF.value, '電子謄本'),
            (cls.TELEX_PDF_DW.value, '電子謄本下載'),
            (cls.QUANTA_PC_ROAD.value, '光特路名'),
            (cls.LOR_V2.value, 'LOR_V2匯入'),
            (cls.V523.value, 'V523匯入'),
            (cls.LOR_V3.value, 'LOR_V3匯入'),
        )
        return CHOICES

class QueryZoneEnum(IntEnum):
    # 查詢分區系統
    # 全國土地使用分區 https://luz.tcd.gov.tw/web/default.aspx
    COUNTRY_LAND_USE_ZONE = 1
    AREA_LAND_USE_ZONE = 2
    LAND_DATA_INPUT = 3
    @classmethod
    def choices(cls):
        CHOICES = (
            (cls.COUNTRY_LAND_USE_ZONE.value, '全國土地使用分區'),
            (cls.AREA_LAND_USE_ZONE.value, '地區土地使用分區'),
            (cls.LAND_DATA_INPUT.value, 'LAND_DATA匯入'),
        )
        return CHOICES


# 土建類別
class LBEnum(IntEnum):
    UNKNOWN = 0
    LAND = 1
    BUILD = 2

    @classmethod
    def choices(cls):
        CHOICES = (
            (cls.LAND.value, '土地'),
            (cls.BUILD.value, '建物'),
        )
        return CHOICES

    @classmethod
    def get(cls, value):
        if value in ['土', '土地', '地號', 'L', 'land']:
            return cls.LAND
        elif value in ['建', '建物', '建號', 'B', 'build']:
            return cls.BUILD

    def __str__(self):
        return ['N', 'L', 'B'][self.value]

# 權利範圍類別
class RightClassifyEnum(IntEnum):
    # 未知
    UNKNOWN = 0
    # 全部
    ALL = 1
    # 持分
    PART = 2
    # 公同共有
    SHARED = 3

    @classmethod
    def choices(cls):
        CHOICES = (
            (cls.UNKNOWN.value, '未知'),
            (cls.ALL.value, '全部'),
            (cls.PART.value, '持分'),
            (cls.SHARED.value, '公同共有'),
        )
        return CHOICES

# 限制登記類別
class RestrictionTypeEnum(IntChoiceEnum):
    # 未限制登記
    NONE = 0
    # 預告登記
    CAUTION = 1
    # 查封登記
    FORECLOSURE = 2
    # 假扣押登記
    PROVISIONAL_ATTACHMENT = 3
    # 假處分登記
    PROVISIONAL_INJUCTION = 4
    # 破產登記
    BANKRUPT = 5
    # 其他依法律所為禁止處分登記
    LAW_PROHIBITED = 6

    @classmethod
    def choices(cls):
        CHOICES = (
            (cls.NONE.value, '未限制登記'),
            (cls.CAUTION.value, '預告登記'),
            (cls.FORECLOSURE.value, '查封登記'),
            (cls.PROVISIONAL_ATTACHMENT.value, '假扣押登記'),
            (cls.PROVISIONAL_INJUCTION.value, '假處分登記'),
            (cls.BANKRUPT.value, '破產登記'),
            (cls.LAW_PROHIBITED.value, '其他依法律所為禁止處分登記'),
        )
        return CHOICES


# 案件類別：
class CaseTypeEnum(IntChoiceEnum):
    # 無設定
    NONE = 0
    # 私設
    PRIVATE = 1
    # 銀行二胎
    BANKS = 2
    # 銀行
    BANK = 3
    # 租賃
    RENTAL = 4
    # 公司
    COMPANY = 5
    # 政府機構
    GOVERMENT = 6

    @classmethod
    def choices(cls):
        CHOICES = (
            (cls.NONE.value, '無設定'),
            (cls.PRIVATE.value, '私設'),
            (cls.BANKS.value, '銀行二胎'),
            (cls.BANK.value, '銀行'),
            (cls.RENTAL.value, '租賃'),
            (cls.COMPANY.value, '公司'),
            (cls.GOVERMENT.value, '政府機構'),
        )
        return CHOICES


class LborTpTypeEnum(IntChoiceEnum):
    LBOR = 1
    TP = 2

    @classmethod
    def choices(cls):
        CHOICES = (
            (cls.LBOR.value, '列表'),
            (cls.TP.value, '謄本'),
        )
        return CHOICES
