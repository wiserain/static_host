# -*- coding: utf-8 -*-
#########################################################
# python
import os
import re
import cgi
import sys
import json
import traceback
from datetime import datetime
try:
    from urllib import urlretrieve
except ImportError:
    from urllib.request import urlretrieve
import shutil
import subprocess
import tarfile, zipfile

# third-party
import werkzeug
from werkzeug.security import generate_password_hash, check_password_hash
from flask import send_from_directory, redirect, request, send_file
from flask.views import View
from flask_login import login_required

# sjva 공용
from framework import db, scheduler, app
from framework.util import Util

# 패키지
from .plugin import logger, package_name
from .model import ModelSetting
from .logic_auth import HTTPBasicAuth

#########################################################


class Logic(object):
    # 디폴트 세팅값
    db_default = {
        'rules': json.dumps({
            '/' + package_name + '/example': {
                'location_path': '/' + package_name + '/example',
                'www_root': os.path.join(os.path.dirname(os.path.abspath(__file__)), 'example'),
                'auth_type': 0,
                'creation_date': datetime.now().isoformat(),
            }
        }),
    }

    @staticmethod
    def db_init():
        try:
            for key, value in Logic.db_default.items():
                if db.session.query(ModelSetting).filter_by(key=key).count() == 0:
                    db.session.add(ModelSetting(key, value))
            db.session.commit()
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def plugin_load():
        try:
            # DB 초기화
            Logic.db_init()

            # 편의를 위해 json 파일 생성
            from .plugin import plugin_info
            Util.save_from_dict_to_json(plugin_info, os.path.join(os.path.dirname(__file__), 'info.json'))

            #
            # 자동시작 옵션이 있으면 보통 여기서
            #
            Logic.register_rules(ModelSetting.get_json('rules'))
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def plugin_unload():
        try:
            logger.debug('%s plugin_unload', package_name)
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    # 기본 구조 End
    ##################################################################
    @staticmethod
    def register_rules(drules):
        for _, v in iter(drules.items()):
            lpath = v['location_path'].rstrip('/')
            wroot = v['www_root']
            atype = v['auth_type']
            endpoint_name = str(lpath.lstrip('/').replace('/', '-'))
            # endpoint_name = str(lpath)
            if wroot.startswith('https://') or wroot.startswith('http://'):
                view_func = RedirectView.as_view(endpoint_name, wroot)
            elif os.path.isfile(wroot):
                view_func = FileView.as_view(endpoint_name, wroot)
            else:
                view_func = StaticView.as_view(endpoint_name, wroot)
            if atype == 1:
                view_func = login_required(view_func)
            elif atype == 2:
                basicauth = HTTPBasicAuth()
                @basicauth.verify_password
                def verify_password(username, password):
                    users = {
                        v['username']: generate_password_hash(v['password'])
                    }
                    if username in users and check_password_hash(users.get(username), password):
                        return username
                view_func = basicauth.login_required(view_func)
            app.add_url_rule(lpath + '/<path:path>', view_func=view_func)
            app.add_url_rule(lpath + '/', view_func=view_func)


    @staticmethod
    def check_lpath(location_path):
        if not location_path.startswith('/'):
            raise ValueError('Location Path는 /로 시작해야 합니다.')

        dangerous_lpath = ['/']
        lpath = location_path.rstrip('/') + '/'
        rules = [str(r) for r in app.url_map.iter_rules() if str(r) not in dangerous_lpath]
        # for rr in sorted(rules):
        #     logger.debug(rr)
        reserved_lpath = [r.split('<')[0].rstrip('/') + '/' for r in rules if '<' in r]
        if any(lpath.startswith(r) for r in reserved_lpath):
            raise ValueError('예약된 Location Path입니다.')
        exact_rules = [r.rstrip('/') + '/' for r in rules if '<' not in r]
        if any(lpath == r for r in exact_rules):
            raise ValueError('이미 등록된 Location Path입니다.')


    @staticmethod
    def install_project(install_cmd, install_dir):
        if len(install_cmd) < 2:
            raise ValueError('잘못된 설치 명령: 설치 URL이 없음')
        was_dir = os.path.isdir(install_dir)
        if not was_dir:
            os.makedirs(install_dir)
        
        try:
            if install_cmd[0] == 'git':
                git_repo = install_cmd[1].split('@')
                git_cmd = ['git', '-C', install_dir, 'clone']
                if len(git_repo) > 1 and git_repo[1]:
                    git_cmd += ['-b', git_repo[1], git_repo[0]]
                else:
                    git_cmd += [git_repo[0]]
                subprocess.check_output(git_cmd, stderr=subprocess.STDOUT)
                basename = re.sub('.git', '', os.path.basename(git_repo[0]), flags=re.IGNORECASE)
                www_root = os.path.join(install_dir, basename)
            elif install_cmd[0] == 'tar':
                temp_fname, headers = urlretrieve(install_cmd[1])
                tar = tarfile.open(temp_fname)
                basename = os.path.commonprefix(tar.getnames())
                if basename:
                    extract_to = install_dir
                else:
                    try:
                        _, params = cgi.parse_header(headers['Content-Disposition'])
                        remote_fname = params['filename']
                    except KeyError:
                        remote_fname = os.path.basename(install_cmd[1])
                    basename = re.sub('.tar', '', remote_fname, flags=re.IGNORECASE)
                    extract_to = os.path.join(install_dir, basename)
                www_root = os.path.join(install_dir, basename)
                tar.extractall(extract_to)
            elif install_cmd[0] == 'zip':
                temp_fname, headers = urlretrieve(install_cmd[1])
                zip = zipfile.ZipFile(temp_fname)
                basename = os.path.commonprefix(zip.namelist())
                if basename:
                    extract_to = install_dir
                else:
                    try:
                        _, params = cgi.parse_header(headers['Content-Disposition'])
                        remote_fname = params['filename']
                    except KeyError:
                        remote_fname = os.path.basename(install_cmd[1])
                    basename = re.sub('.zip', '', remote_fname, flags=re.IGNORECASE)
                    extract_to = os.path.join(install_dir, basename)
                www_root = os.path.join(install_dir, basename)
                zip.extractall(extract_to)
            else:
                raise NotImplementedError('지원하지 않는 설치 명령: %s' % install_cmd[0])

            if len(install_cmd) > 2 and install_cmd[2]:
                www_root = os.path.join(www_root, install_cmd[2])

            return www_root
        except subprocess.CalledProcessError as e:
            if not was_dir:
                shutil.rmtree(install_dir)
            raise Exception(e.output.strip())
        except Exception as e:
            if not was_dir:
                shutil.rmtree(install_dir)
            raise e


class StaticView(View):
    methods = ['GET']

    def __init__(self, host_root):
        self.host_root = host_root

    def dispatch_request(self, path='index.html'):
        try:
            if path == 'favicon.ico':
                return send_from_directory(self.host_root, path, mimetype='image/vnd.microsoft.icon')
            else:
                return send_from_directory(self.host_root, path)
        except werkzeug.exceptions.NotFound as e:
            current_root = os.path.join(self.host_root, path)
            if os.path.isdir(current_root) and not path.endswith('/'):
                return redirect(path + '/', code=301)
            if path.endswith('/'):
                return send_from_directory(current_root, 'index.html')
            raise e


class RedirectView(View):
    methods = ['GET']

    def __init__(self, redirect_to):
        self.redirect_to = redirect_to

    def dispatch_request(self):
        return redirect(self.redirect_to)


class FileView(View):
    methods = ['GET']

    def __init__(self, filepath):
        self.filepath = filepath

    def dispatch_request(self):
        return send_file(self.filepath, as_attachment=True)
