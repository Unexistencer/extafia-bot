from enum import Enum
from dataclasses import dataclass

PREFIX_WHITELIST = {
    "h",
    "lang",
    "stat",
    "choose",
    "vhs",
    "enchant",
    "vaal",
    "arena",
    "announce",
}

class Language(Enum):
    ZH = "zh"
    EN = "en"
    JP = "jp"

class Category(Enum):
    LANG = "lang"
    STATUS = "status"
    CHOOSE = "choose"
    ANNOUNCE = "announce"
    ARENA = "arena"
    ENCHANT = "enchant"
    VAAL = "vaal"

class SubCategory(Enum):
    TITLE = "title"
    DESCRIPTION = "description"

class CommandStatus(Enum):
    AVAILABLE = "Available"
    MAINTENANCE = "In Maintenance"
    WIP = "Work In Progress"
    UNAVAILABLE = "Unavailable"
    HIDDEN = "Hidden"

class Command(Enum):
    SYS          = ("sys", CommandStatus.HIDDEN)
    MODE         = ("mode", CommandStatus.HIDDEN)
    WHITELIST    = ("whitelist", CommandStatus.HIDDEN)
    DEVELOPER    = ("developer", CommandStatus.HIDDEN)

    HELP         = ("info", CommandStatus.HIDDEN)
    LANG         = ("lang", CommandStatus.AVAILABLE)
    STATUS       = ("stat", CommandStatus.AVAILABLE)
    CHOOSE       = ("choose", CommandStatus.AVAILABLE)
    VHS          = ("vhs", CommandStatus.AVAILABLE)
    ENCHANT      = ("enchant", CommandStatus.AVAILABLE)
    VAAL         = ("vaal", CommandStatus.AVAILABLE)
    ARENA        = ("arena", CommandStatus.AVAILABLE)
    ANNOUNCE     = ("announce", CommandStatus.WIP)

    def __init__(self, command_name, status):
        self.command_name = command_name
        self.status = status
    
class Cost:
    ENCHANT = 1000
    VAAL = 10000

class Special_Vaal:
    normal = 10000
    success = 20000
    nerf = 30000


@dataclass
class SeasonalData:
    arena_playcount: int = 0
    win_count: int = 0
    eightD_count: int = 0
    longest: int = 0

    @classmethod
    def from_doc(cls, value) -> "SeasonalData":
        return cls(
            arena_playcount = int(value.get("arena_playcount", 0)),
            win_count       = int(value.get("win_count", 0)),
            eightD_count    = int(value.get("eightD_count", 0)),
            longest         = int(value.get("longest", 0))
        )

    def to_dict(self) -> dict:
        return {
            "arena_playcount": self.arena_playcount,
            "win_count": self.win_count,
            "eightD_count": self.eightD_count,
            "longest": self.longest
        }


@dataclass
class TotalData:
    total_currency: int = 0
    total_arena_count: int = 0
    total_win_count: int = 0
    total_8D_count: int = 0
    total_longest: int = 0

    @classmethod
    def from_doc(cls, value) -> "TotalData":
        return cls(
            total_currency     = int(value.get("total_currency", 0)),
            total_arena_count  = int(value.get("total_arena_count", 0)),
            total_win_count    = int(value.get("total_win_count", 0)),
            total_8D_count     = int(value.get("total_8D_count", 0)),
            total_longest      = int(value.get("total_longest", 0))
        )

    def to_dict(self) -> dict:
        return {
            "total_currency": self.total_currency,
            "total_arena_count": self.total_arena_count,
            "total_win_count": self.total_win_count,
            "total_8D_count": self.total_8D_count,
            "total_longest": self.total_longest
        }
