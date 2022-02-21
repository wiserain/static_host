import os

# third-party
from flask import Blueprint

# pylint: disable=import-error
from framework import app, path_data
from framework.util import Util
from framework.logger import get_logger
from framework.common.plugin import get_model_setting, Logic, default_route_single_module


class PlugIn:
    package_name = __name__.split(".", maxsplit=1)[0]
    logger = get_logger(package_name)
    ModelSetting = get_model_setting(package_name, logger, table_name=f"plugin_{package_name}_setting")

    blueprint = Blueprint(
        package_name,
        package_name,
        url_prefix=f"/{package_name}",
        template_folder=os.path.join(os.path.dirname(__file__), "templates"),
    )

    menu = {
        "main": [package_name, "정적 호스트"],
        "sub": [["setting", "설정"], ["log", "로그"]],
        "category": "tool",
    }
    home_module = "setting"

    plugin_info = {
        "category_name": "tool",
        "version": "0.1.2",
        "name": "static_host",
        "home": "https://github.com/wiserain/static_host",
        "more": "https://github.com/wiserain/static_host",
        "description": "로컬 폴더를 정적 웹으로 호스팅 하는 플러그인",
        "developer": "wiserain",
        "zip": "https://github.com/wiserain/static_host/archive/master.zip",
        "icon": "",
    }

    module_list = None
    logic = None

    def __init__(self):
        db_file = os.path.join(path_data, "db", f"{self.package_name}.db")
        app.config["SQLALCHEMY_BINDS"][self.package_name] = f"sqlite:///{db_file}"

        Util.save_from_dict_to_json(self.plugin_info, os.path.join(os.path.dirname(__file__), "info.json"))


plugin = PlugIn()

# pylint: disable=relative-beyond-top-level
from .logic import LogicMain

plugin.module_list = [LogicMain(plugin)]

# (logger, package_name, module_list, ModelSetting) required for Logic
plugin.logic = Logic(plugin)
# (;ogger, package_name, module_list, ModelSetting, blueprint, logic) required for default_route
default_route_single_module(plugin)
