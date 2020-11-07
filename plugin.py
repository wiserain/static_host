# -*- coding: utf-8 -*-
#########################################################
# 고정영역
#########################################################
# python
import os
import traceback
from datetime import datetime
import shutil

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

from .logic import Logic
from .model import ModelSetting

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
    "version": "0.0.3",
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
        arg['project_template_list'] = [
            ['', '선택하면 설치 명령이 자동 완성됩니다.'],
            ['git|https://github.com/codedread/kthoom', 'https://github.com/codedread/kthoom'],
            ['git|https://github.com/daleharvey/pacman', 'https://github.com/daleharvey/pacman'],
            ['git|https://github.com/ziahamza/webui-aria2|docs', 'https://github.com/ziahamza/webui-aria2'],
            ['git|https://github.com/SauravKhare/speedtest', 'https://github.com/SauravKhare/speedtest'],
            ['tar|https://github.com/viliusle/miniPaint/archive/v4.2.4.tar.gz', 'https://github.com/viliusle/miniPaint'],
            ['zip|https://github.com/mayswind/AriaNg/releases/download/1.1.6/AriaNg-1.1.6.zip', 'https://github.com/mayswind/AriaNg'],
        ]
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
    try:
        p = request.form.to_dict() if request.method == 'POST' else request.args.to_dict()
        if sub == 'add_rule':
            lpath = p.get('location_path', '')
            Logic.check_lpath(lpath)

            if p.get('use_project_install') == 'True':
                install_cmd = p.get('project_install_cmd').split('|')
                install_dir = p.get('project_install_dir')
                www_root = Logic.install_project(install_cmd, install_dir)
            else:
                www_root = p.get('www_root', '')
                if not os.path.isdir(www_root):
                    raise ValueError('존재하지 않는 디렉토리 경로입니다.')
            
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
        elif sub == 'rule':
            act = p.get('act', '')
            ret = p.get('ret', 'list')
            lpath = p.get('location_path', '')
            drules = ModelSetting.get_json('rules')
            
            # apply action
            if act == 'del' or act == 'pur':
                if lpath in drules:
                    if act == 'pur':
                        shutil.rmtree(drules[lpath]['www_root'])
                    del drules[lpath]

            if act:
                ModelSetting.set_json('rules', drules)

            lrules = [val for _, val in iter(drules.items())]
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
                raise NotImplementedError('Unknown return type: %s' % ret)
        elif sub == 'check_dir':
            dir = p.get('dir', '')
            if os.path.isdir(dir):
                list_dir = os.listdir(dir)
                in_total = len(list_dir)
                export_only = 5
                if in_total > export_only:
                    list_dir = list_dir[:export_only] + ['and %s more ...' % (in_total-export_only)]
                return jsonify({'success': True, 'len': in_total, 'list': list_dir})
            else:
                return jsonify({'success': True, 'len': -1})
    except Exception as e:
        logger.error('Exception:%s', e)
        logger.error(traceback.format_exc())
        return jsonify({'success': False, 'log': str(e)})
