import os
import re
import cgi
import json
import traceback
from datetime import datetime
from urllib.request import urlretrieve
import shutil
import subprocess
import tarfile
import zipfile

# third-party
from werkzeug.exceptions import NotFound
from werkzeug.security import check_password_hash, generate_password_hash
from flask import send_from_directory, redirect, request, send_file, render_template, jsonify
from flask.views import View
from flask_login import login_required

# pylint: disable=import-error
from framework import app, SystemModelSetting
from framework.common.plugin import LogicModuleBase

# local
from .plugin import plugin
from .logic_auth import HTTPBasicAuth

logger = plugin.logger
package_name = plugin.package_name
ModelSetting = plugin.ModelSetting


class LogicMain(LogicModuleBase):
    db_default = {
        "rules": json.dumps(
            {
                f"/{package_name}/example": {
                    "location_path": f"/{package_name}/example",
                    "www_root": os.path.join(os.path.dirname(os.path.abspath(__file__)), "example"),
                    "auth_type": 0,
                    "creation_date": datetime.now().isoformat(),
                }
            }
        ),
    }

    def __init__(self, P):
        super().__init__(P, None)

    def plugin_load(self):
        try:
            LogicMain.register_rules(json.loads(ModelSetting.get("rules")))
        except Exception as e:
            logger.error("Exception:%s", e)
            logger.error(traceback.format_exc())

    def process_menu(self, sub, req):
        arg = ModelSetting.to_dict()
        if sub == "setting":
            arg["package_name"] = package_name
            arg["rule_size"] = len(json.loads(ModelSetting.get("rules")))
            arg["ddns"] = SystemModelSetting.get("ddns").rstrip("/")
            arg["project_template_list"] = [
                ["", "선택하면 설치 명령이 자동 완성됩니다."],
                ["git|https://github.com/codedread/kthoom", "https://github.com/codedread/kthoom"],
                ["git|https://github.com/daleharvey/pacman", "https://github.com/daleharvey/pacman"],
                ["git|https://github.com/ziahamza/webui-aria2|docs", "https://github.com/ziahamza/webui-aria2"],
                ["git|https://github.com/SauravKhare/speedtest", "https://github.com/SauravKhare/speedtest"],
                [
                    "tar|https://github.com/viliusle/miniPaint/archive/v4.9.3.tar.gz",
                    "https://github.com/viliusle/miniPaint",
                ],
                [
                    "zip|https://github.com/mayswind/AriaNg/releases/download/1.2.3/AriaNg-1.2.3.zip",
                    "https://github.com/mayswind/AriaNg",
                ],
            ]
            return render_template(f"{package_name}_{sub}.html", sub=sub, arg=arg)
        return render_template("sample.html", title=f"{package_name} - {sub}")

    def process_ajax(self, sub, req):
        try:
            p = request.form.to_dict() if request.method == "POST" else request.args.to_dict()
            if sub == "add_rule":
                lpath = p.get("location_path", "")
                LogicMain.check_lpath(lpath)

                if p.get("use_project_install") == "True":
                    install_cmd = p.get("project_install_cmd").split("|")
                    install_dir = p.get("project_install_dir")
                    www_root = LogicMain.install_project(install_cmd, install_dir)
                else:
                    www_root = p.get("www_root", "")
                    if not www_root.startswith(("https://", "http://")):
                        if not os.path.exists(www_root):
                            raise ValueError("존재하지 않는 경로입니다.")

                new_rule = {
                    "location_path": lpath,
                    "www_root": www_root,
                    "auth_type": int(p.get("auth_type")),
                    "creation_date": datetime.now().isoformat(),
                }

                if p.get("auth_type") == "2":
                    if not (p.get("username") and p.get("password")):
                        raise ValueError("USER/PASS를 입력하세요.")
                    new_rule.update(
                        {
                            "username": p.get("username"),
                            "password": generate_password_hash(p.get("password")),
                        }
                    )

                LogicMain.register_rules({lpath: new_rule})

                drules = json.loads(ModelSetting.get("rules"))
                drules.update({lpath: new_rule})
                ModelSetting.set("rules", json.dumps(drules))

                return jsonify({"success": True, "ret": new_rule})
            if sub == "rule":
                act = p.get("act", "")
                ret = p.get("ret", "list")
                lpath = p.get("location_path", "")
                drules = json.loads(ModelSetting.get("rules"))

                # apply action
                if act in ["del", "pur"] and lpath in drules:
                    if act == "pur" and os.path.isdir(drules[lpath]["www_root"]):
                        shutil.rmtree(drules[lpath]["www_root"])
                    elif act == "pur" and os.path.isfile(drules[lpath]["www_root"]):
                        os.remove(drules[lpath]["www_root"])
                    del drules[lpath]

                if act:
                    ModelSetting.set("rules", json.dumps(drules))

                lrules = [val for _, val in iter(drules.items())]
                if ret == "count":
                    return jsonify({"success": True, "ret": len(lrules)})
                if ret == "list":
                    lrules = sorted(lrules, key=lambda x: x["creation_date"], reverse=True)
                    counter = int(p.get("c", "0"))
                    pagesize = 20
                    if counter == 0:
                        lrules = lrules[:pagesize]
                    elif counter == len(lrules):
                        lrules = []
                    else:
                        lrules = lrules[counter : counter + pagesize]
                    return jsonify({"success": True, "ret": lrules, "nomore": len(lrules) != pagesize})
                raise NotImplementedError(f"Unknown return type: {ret}")
            if sub == "check_path":
                path = p.get("path", "")
                ret = {"success": True, "exists": os.path.exists(path), "isfile": os.path.isfile(path)}
                if os.path.isdir(path):
                    ret.update({"isdir": True})
                else:
                    ret.update({"isdir": False})
                return jsonify(ret)
            raise NotImplementedError(f"Unknown sub type: {sub}")
        except Exception as e:
            logger.error("Exception:%s", e)
            logger.error(traceback.format_exc())
            return jsonify({"success": False, "log": str(e)})

    @staticmethod
    def register_rules(drules):
        for _, v in iter(drules.items()):
            lpath = v["location_path"].rstrip("/")
            wroot = v["www_root"]
            atype = v["auth_type"]
            endpoint_name = str(lpath.lstrip("/").replace("/", "-"))
            # endpoint_name = str(lpath)
            if wroot.startswith(("https://", "http://")):
                view_func = RedirectView.as_view(endpoint_name, wroot)
            elif os.path.isfile(wroot):
                view_func = FileView.as_view(endpoint_name, wroot)
            else:
                view_func = StaticView.as_view(endpoint_name, wroot)
            if atype == 1:
                view_func = login_required(view_func)
            elif atype == 2:
                basicauth = LogicMain.get_basicauth({v["username"]: v["password"]})
                view_func = basicauth.login_required(view_func)
            if os.path.isdir(wroot):
                app.add_url_rule(lpath + "/<path:path>", view_func=view_func)
                app.add_url_rule(lpath + "/", view_func=view_func)
            else:
                app.add_url_rule(lpath, view_func=view_func)

    @staticmethod
    def check_lpath(location_path):
        if not location_path.startswith("/"):
            raise ValueError("Location Path는 /로 시작해야 합니다.")

        dangerous_lpath = ["/"]
        lpath = location_path.rstrip("/") + "/"
        rules = [str(r) for r in app.url_map.iter_rules() if str(r) not in dangerous_lpath]
        # for rr in sorted(rules):
        #     logger.debug(rr)
        reserved_lpath = [r.split("<")[0].rstrip("/") + "/" for r in rules if "<" in r]
        if any(lpath.startswith(r) for r in reserved_lpath):
            raise ValueError("예약된 Location Path입니다.")
        exact_rules = [r.rstrip("/") + "/" for r in rules if "<" not in r]
        if any(lpath == r for r in exact_rules):
            raise ValueError("이미 등록된 Location Path입니다.")

    @staticmethod
    def install_project(install_cmd, install_dir):
        if len(install_cmd) < 2:
            raise ValueError("잘못된 설치 명령: 설치 URL이 없음")
        was_dir = os.path.isdir(install_dir)
        if not was_dir:
            os.makedirs(install_dir)

        try:
            if install_cmd[0] == "git":
                git_repo = install_cmd[1].split("@")
                git_cmd = ["git", "-C", install_dir, "clone"]
                if len(git_repo) > 1 and git_repo[1]:
                    git_cmd += ["-b", git_repo[1], git_repo[0]]
                else:
                    git_cmd += [git_repo[0]]
                subprocess.check_output(git_cmd, stderr=subprocess.STDOUT)
                basename = re.sub(".git", "", os.path.basename(git_repo[0]), flags=re.IGNORECASE)
                www_root = os.path.join(install_dir, basename)
            elif install_cmd[0] == "tar":
                temp_fname, headers = urlretrieve(install_cmd[1])
                with tarfile.open(temp_fname) as _t:
                    basename = os.path.commonprefix(_t.getnames())
                    if basename:
                        extract_to = install_dir
                    else:
                        try:
                            _, params = cgi.parse_header(headers["Content-Disposition"])
                            remote_fname = params["filename"]
                        except KeyError:
                            remote_fname = os.path.basename(install_cmd[1])
                        basename = re.sub(".tar", "", remote_fname, flags=re.IGNORECASE)
                        extract_to = os.path.join(install_dir, basename)
                    www_root = os.path.join(install_dir, basename)
                    _t.extractall(extract_to)
            elif install_cmd[0] == "zip":
                temp_fname, headers = urlretrieve(install_cmd[1])
                with zipfile.ZipFile(temp_fname) as _z:
                    basename = os.path.commonprefix(_z.namelist())
                    if basename:
                        extract_to = install_dir
                    else:
                        try:
                            _, params = cgi.parse_header(headers["Content-Disposition"])
                            remote_fname = params["filename"]
                        except KeyError:
                            remote_fname = os.path.basename(install_cmd[1])
                        basename = re.sub(".zip", "", remote_fname, flags=re.IGNORECASE)
                        extract_to = os.path.join(install_dir, basename)
                    www_root = os.path.join(install_dir, basename)
                    _z.extractall(extract_to)
            else:
                raise NotImplementedError(f"지원하지 않는 설치 명령: {install_cmd[0]}")

            if len(install_cmd) > 2 and install_cmd[2]:
                www_root = os.path.join(www_root, install_cmd[2])

            return www_root
        except subprocess.CalledProcessError as e:
            if not was_dir:
                shutil.rmtree(install_dir)
            raise Exception(e.output.strip()) from e
        except Exception as e:
            if not was_dir:
                shutil.rmtree(install_dir)
            raise e

    @staticmethod
    def get_basicauth(users):
        basicauth = HTTPBasicAuth()

        @basicauth.verify_password
        def verify_password(username, password):
            if username in users and check_password_hash(users.get(username), password):
                return username
            return False

        return basicauth


class StaticView(View):
    methods = ["GET"]

    def __init__(self, host_root):
        self.host_root = host_root

    def dispatch_request(self, path="index.html"):
        try:
            if path == "favicon.ico":
                return send_from_directory(self.host_root, path, mimetype="image/vnd.microsoft.icon")
            return send_from_directory(self.host_root, path)
        except NotFound as e:
            current_root = os.path.join(self.host_root, path)
            if os.path.isdir(current_root) and not path.endswith("/"):
                return redirect(path + "/", code=301)
            if path.endswith("/"):
                return send_from_directory(current_root, "index.html")
            raise e


class RedirectView(View):
    methods = ["GET"]

    def __init__(self, redirect_to):
        self.redirect_to = redirect_to

    def dispatch_request(self):
        return redirect(self.redirect_to)


class FileView(View):
    methods = ["GET"]

    def __init__(self, filepath):
        self.filepath = filepath

    def dispatch_request(self):
        return send_file(self.filepath, as_attachment=True)
