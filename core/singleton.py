# core/singleton.py
from abc import ABCMeta


class SingletonABCMeta(ABCMeta):
    """
    Metaclass gabungan: Singleton + ABCMeta.
    Menggabungkan keduanya agar tidak ada konflik metaclass saat
    BaseETL mewarisi sifat Singleton sekaligus bisa pakai @abstractmethod.
    """
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            instance = super().__call__(*args, **kwargs)
            cls._instances[cls] = instance
        return cls._instances[cls]


class BaseSingleton(metaclass=SingletonABCMeta):
    """
    Base class pembantu.
    Cukup inherit class ini agar otomatis Singleton
    dan kompatibel dengan @abstractmethod.
    """
    pass
