# -*- coding: utf-8 -*-
#########################################################
# python
import os
import re
import sys
import json
import traceback
from datetime import datetime
# third-party
import werkzeug
from flask import send_from_directory, redirect, request
from flask.views import View
from flask_login import login_required

# sjva 공용
from framework import db, scheduler, app
from framework.util import Util

# 패키지
from .plugin import logger, package_name
from .model import ModelSetting

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
            from plugin import plugin_info
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

    @staticmethod
    def setting_save(req):
        try:
            for key, value in req.form.items():
                logger.debug('Key:%s Value:%s', key, value)
                entity = db.session.query(ModelSetting).filter_by(key=key).with_for_update().first()
                entity.value = value
            db.session.commit()
            return True
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return False

    # 기본 구조 End
    ##################################################################
    @staticmethod
    def register_rules(drules):
        for _, v in drules.iteritems():
            lpath = v['location_path'].rstrip('/')
            wroot = v['www_root']
            atype = v['auth_type']
            endpoint_name = str(lpath.lstrip('/').replace('/', '-'))
            # endpoint_name = str(lpath)
            if atype == 0:
                view_func = StaticView.as_view(endpoint_name, wroot)
            elif atype == 1:
                view_func = StaticViewSJVAAuth.as_view(endpoint_name, wroot)
            else:
                raise NotImplementedError('auth_type: %s' % atype)
            app.add_url_rule(lpath + '/<path:path>', view_func=view_func)
            app.add_url_rule(lpath + '/', view_func=view_func)


    @staticmethod
    def is_already_registered(location_path):
        rules = [str(r) for r in app.url_map.iter_rules()]
        rules = [r.split('<')[0].rstrip('/') + '/' for r in rules if r != '/']
        lpath = location_path.rstrip('/') + '/'
        return any(lpath.startswith(r) for r in rules)


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


class StaticViewSJVAAuth(View):
    methods = ['GET']
    decorators = [login_required]

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
