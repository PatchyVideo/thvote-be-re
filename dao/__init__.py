"""
后端的DAO模型。

定义了各种需要在前后端间传输的数据类。
"""
from .login_data import LoginData
from .register_data import RegisterData

__version__ = "1.0.0"
__author__ = "FunnyAWM"
__all__ = [
    "LoginData",
    "RegisterData"
]
