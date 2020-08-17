# -*- coding: utf-8 -*-
#########################################################
# 고정영역
#########################################################
# python
import os
import traceback
from datetime import datetime

# third-party
from flask import Blueprint, request, render_template, redirect, jsonify, Response
from flask_login import login_required

# sjva 공용
from framework.logger import get_logger
from framework import app, db, scheduler, check_api
from system.model import ModelSetting as SystemModelSetting

# 패키지
package_name = __name__.split('.')[0]
logger = get_logger(package_name)

from logic import Logic
from model import ModelSetting

blueprint = Blueprint(
    package_name, package_name,
    url_prefix='/%s' % package_name,
    template_folder=os.path.join(os.path.dirname(__file__), 'templates')
)


def plugin_load():
    Logic.plugin_load()


def plugin_unload():
    Logic.plugin_unload()


plugin_info = {
    "category_name": "tool",
    "version": "0.0.1",
    "name": "static_host",
    "home": "https://github.com/wiserain/static_host",
    "more": "https://github.com/wiserain/static_host",
    "description": "로컬 폴더를 정적 웹으로 호스팅 하는 SJVA 플러그인",
    "developer": "wiserain",
    "zip": "https://github.com/wiserain/static_host/archive/master.zip",
    "icon": "",
}
#########################################################


# 메뉴 구성.
menu = {
    'main': [package_name, '정적 호스트'],
    'sub': [
        ['setting', '설정'], ['log', '로그']
    ],
    'category': 'tool',
}


#########################################################
# WEB Menu
#########################################################
@blueprint.route('/')
def home():
    return redirect('/%s/setting' % package_name)


@blueprint.route('/<sub>')
@login_required
def detail(sub):
    if sub == 'setting':
        arg = ModelSetting.to_dict()
        arg['package_name'] = package_name
        arg['rule_size'] = len(ModelSetting.get_json('rules'))
        arg['ddns'] = SystemModelSetting.get('ddns').rstrip('/')
        return render_template('%s_setting.html' % package_name, sub=sub, arg=arg)
    elif sub == 'log':
        return render_template('log.html', package=package_name)
    return render_template('sample.html', title='%s - %s' % (package_name, sub))


#########################################################
# For UI                                                          
#########################################################
@blueprint.route('/ajax/<sub>', methods=['GET', 'POST'])
@login_required
def ajax(sub):
    # 설정 저장
    if sub == 'setting_save':
        try:
            ret = Logic.setting_save(request)
            return jsonify(ret)
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
    elif sub == 'add_rule':
        try:
            p = request.form.to_dict() if request.method == 'POST' else request.args.to_dict()
            lpath = p.get('location_path', '')
            www_root = p.get('www_root', '')

            if not lpath.startswith('/'):
                return jsonify({'success': False, 'log': 'Location path는 /로 시작해야 합니다.'})
            if Logic.is_already_registered(lpath):
                return jsonify({'success': False, 'log': '이미 사용 중인 Location path입니다.'})            
            if not os.path.isdir(www_root):
                return jsonify({'success': False, 'log': '존재하지 않는 디렉토리 경로입니다.'})

            new_rule = {
                'location_path': lpath,
                'www_root': www_root,
                'auth_type': int(p.get('auth_type')),
                'creation_date': datetime.now().isoformat(),
            }
            Logic.register_rules({lpath: new_rule})

            drules = ModelSetting.get_json('rules')
            drules.update({lpath: new_rule})
            ModelSetting.set_json('rules', drules)

            return jsonify({'success': True, 'ret': new_rule})
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return jsonify({'success': False, 'log': str(e)})
    elif sub == 'rule':
        try:
            p = request.form.to_dict() if request.method == 'POST' else request.args.to_dict()
            act = p.get('act', '')
            ret = p.get('ret', 'list')
            lpath = p.get('location_path', '')
            drules = ModelSetting.get_json('rules')
            
            # apply action
            if act == 'del' and lpath:
                if lpath in drules:
                    del drules[lpath]
            elif act == 'clear':
                drules.clear()

            if act:
                ModelSetting.set_json('rules', drules)

            lrules = [val for _, val in drules.iteritems()]
            if ret == 'count':
                return jsonify({'success': True, 'ret': len(lrules)})
            elif ret == 'list':
                lrules = sorted(lrules, key=lambda x: x['creation_date'], reverse=True)
                if p.get('c', ''):
                    counter = int(p.get('c'))
                    pagesize = 20
                    if counter == 0:
                        lrules = lrules[:pagesize]
                    elif counter == len(lrules):
                        lrules = []
                    else:
                        lrules = lrules[counter:counter+pagesize]
                return jsonify({'success': True, 'ret': lrules})
            else:
                return jsonify({'success': False, 'log': 'Unknown return type: %s' % ret})
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return jsonify({'success': False, 'log': str(e)})
