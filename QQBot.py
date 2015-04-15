# -*- coding: utf-8 -*-

import re
import random
import json
import os
import sys
import datetime
import time
import threading
import logging
import urllib
from HttpClient import HttpClient

reload(sys)
sys.setdefaultencoding("utf-8")

HttpClient_Ist = HttpClient()

ClientID = int(random.uniform(111111, 888888))
PTWebQQ = ''
APPID = 0
msgId = 0
FriendList = {}
GroupList = {}
ThreadList = []
GroupThreadList = []
GroupWatchList = []
PSessionID = ''
Referer = 'http://d.web2.qq.com/proxy.html?v=20130916001&callback=1&id=2'
SmartQQUrl = 'http://w.qq.com/login.html'
VFWebQQ = ''
AdminQQ = '0'
tulingkey=#'YOUR KEY HERE'#

initTime = time.time()


logging.basicConfig(filename='log.log', level=logging.DEBUG, format='%(asctime)s  %(filename)s[line:%(lineno)d] %(levelname)s %(message)s', datefmt='%a, %d %b %Y %H:%M:%S')

# -----------------
# 方法声明
# -----------------


def pass_time():
    global initTime
    rs = (time.time() - initTime)
    initTime = time.time()
    return str(round(rs, 3))


def getReValue(html, rex, er, ex):
    v = re.search(rex, html)

    if v is None:
        logging.error(er)

        if ex:
            raise Exception, er
        return ''

    return v.group(1)


def date_to_millis(d):
    return int(time.mktime(d.timetuple())) * 1000


# 查询QQ号，通常首次用时0.2s，以后基本不耗时
def uin_to_account(tuin):
    # 如果消息的发送者的真实QQ号码不在FriendList中,则自动去取得真实的QQ号码并保存到缓存中
    global FriendList
    if tuin not in FriendList:
        try:
            info = json.loads(HttpClient_Ist.Get('http://s.web2.qq.com/api/get_friend_uin2?tuin={0}&type=1&vfwebqq={1}'.format(tuin, VFWebQQ), Referer))
            logging.info("Get uin to account info:" + str(info))
            if info['retcode'] != 0:
                raise ValueError, info
            info = info['result']
            FriendList[tuin] = info['account']

        except Exception as e:
            logging.error(e)

    logging.info("Now FriendList:" + str(FriendList))
    return FriendList[tuin]


def msg_handler(msgObj):
    for msg in msgObj:
        msgType = msg['poll_type']

        # QQ私聊消息
        if msgType == 'message' or msgType == 'sess_message':  # 私聊 or 临时对话
            txt = combine_msg(msg['value']['content'])
            tuin = msg['value']['from_uin']
            from_account = uin_to_account(tuin)

            # print "{0}:{1}".format(from_account, txt)
            targetThread = thread_exist(from_account)
            if targetThread:
                targetThread.push(txt)
            else:
                tmpThread = pmchat_thread(tuin)
                tmpThread.start()
                ThreadList.append(tmpThread)
                tmpThread.push(txt)

            # print "{0}:{1}".format(self.FriendList.get(tuin, 0), txt)

            # if FriendList.get(tuin, 0) == AdminQQ:#如果消息的发送者与AdminQQ不相同, 则忽略本条消息不往下继续执行
            #     if txt[0] == '#':
            #         thread.start_new_thread(self.runCommand, (tuin, txt[1:].strip(), msgId))
            #         msgId += 1

            # if txt[0:4] == 'exit':
            #     logging.info(self.Get('http://d.web2.qq.com/channel/logout2?ids=&clientid={0}&psessionid={1}'.format(self.ClientID, self.PSessionID), Referer))
            #     exit(0)

        # 群消息
        if msgType == 'group_message':
            global GroupList, GroupWatchList
            txt = combine_msg(msg['value']['content'])
            guin = msg['value']['from_uin']
            gid = msg['value']['info_seq']
            tuin = msg['value']['send_uin']
            seq = msg['value']['seq']
            GroupList[guin] = gid
            if str(gid) in GroupWatchList:
                g_exist = group_thread_exist(gid)
                if g_exist:
                    g_exist.handle(tuin, txt, seq)
                else:
                    tmpThread = group_thread(guin)
                    tmpThread.start()
                    GroupThreadList.append(tmpThread)
                    tmpThread.handle(tuin, txt, seq)
                    logging.info("群线程已生成")
            else:
                logging.info(str(gid) + "群有动态，但是没有被监控")

            # from_account = uin_to_account(tuin)
            # print "{0}:{1}".format(from_account, txt)

        # QQ号在另一个地方登陆, 被挤下线
        if msgType == 'kick_message':
            logging.error(msg['value']['reason'])
            raise Exception, msg['value']['reason']  # 抛出异常, 重新启动WebQQ, 需重新扫描QRCode来完成登陆


def combine_msg(content):
    msgTXT = ""
    for part in content:
        # print type(part)
        if type(part) == type(u'\u0000'):
            msgTXT += part
        elif len(part) > 1:
            # 如果是图片
            if str(part[0]) == "offpic" or str(part[0]) == "cface":
                msgTXT += "[图片]"

    return msgTXT


def send_msg(tuin, content):
    reqURL = "http://d.web2.qq.com/channel/send_buddy_msg2"
    data = (
        ('r', '{{"to":{0}, "face":594, "content":"[\\"{4}\\", [\\"font\\", {{\\"name\\":\\"Arial\\", \\"size\\":\\"10\\", \\"style\\":[0, 0, 0], \\"color\\":\\"000000\\"}}]]", "clientid":"{1}", "msg_id":{2}, "psessionid":"{3}"}}'.format(tuin, ClientID, msgId, PSessionID, str(content))),
        ('clientid', ClientID),
        ('psessionid', PSessionID)
    )
    rsp = HttpClient_Ist.Post(reqURL, data, Referer)

    return rsp


def thread_exist(tqq):
    for t in ThreadList:
        if t.tqq == tqq:
            return t
    return False


def group_thread_exist(gid):
    for t in GroupThreadList:
        if str(t.gid) == str(gid):
            return t
    return False

# -----------------
# 类声明
# -----------------


class Login(HttpClient):
    MaxTryTime = 5

    def __init__(self, vpath, qq=0):
        global APPID, AdminQQ, PTWebQQ, VFWebQQ, PSessionID, msgId
        self.VPath = vpath  # QRCode保存路径
        AdminQQ = int(qq)
        logging.critical("正在获取登陆页面")
        self.initUrl = getReValue(self.Get(SmartQQUrl), r'\.src = "(.+?)"', 'Get Login Url Error.', 1)
        html = self.Get(self.initUrl + '0')

        logging.critical("正在获取appid")
        APPID = getReValue(html, r'var g_appid =encodeURIComponent\("(\d+)"\);', 'Get AppId Error', 1)
        logging.critical("正在获取login_sig")
        sign = getReValue(html, r'var g_login_sig=encodeURIComponent\("(.+?)"\);', 'Get Login Sign Error', 0)
        logging.info('get sign : %s', sign)
        logging.critical("正在获取pt_version")
        JsVer = getReValue(html, r'var g_pt_version=encodeURIComponent\("(\d+)"\);', 'Get g_pt_version Error', 1)
        logging.info('get g_pt_version : %s', JsVer)
        logging.critical("正在获取mibao_css")
        MiBaoCss = getReValue(html, r'var g_mibao_css=encodeURIComponent\("(.+?)"\);', 'Get g_mibao_css Error', 1)
        logging.info('get g_mibao_css : %s', sign)
        StarTime = date_to_millis(datetime.datetime.utcnow())

        T = 0
        while True:
            T = T + 1
            self.Download('https://ssl.ptlogin2.qq.com/ptqrshow?appid={0}&e=0&l=L&s=8&d=72&v=4'.format(APPID), self.VPath)
            
            logging.info('[{0}] Get QRCode Picture Success.'.format(T))
            

            while True:
                html = self.Get('https://ssl.ptlogin2.qq.com/ptqrlogin?webqq_type=10&remember_uin=1&login2qq=1&aid={0}&u1=http%3A%2F%2Fw.qq.com%2Fproxy.html%3Flogin2qq%3D1%26webqq_type%3D10&ptredirect=0&ptlang=2052&daid=164&from_ui=1&pttype=1&dumy=&fp=loginerroralert&action=0-0-{1}&mibao_css={2}&t=undefined&g=1&js_type=0&js_ver={3}&login_sig={4}'.format(APPID, date_to_millis(datetime.datetime.utcnow()) - StarTime, MiBaoCss, JsVer, sign), self.initUrl)
                # logging.info(html)
                ret = html.split("'")
                if ret[1] == '65' or ret[1] == '0':  # 65: QRCode 失效, 0: 验证成功, 66: 未失效, 67: 验证中
                    break
                time.sleep(2)
            if ret[1] == '0' or T > self.MaxTryTime:
                break

        logging.info(ret)
        if ret[1] != '0':
            return
        logging.critical("二维码已扫描，正在登陆")
        pass_time()
        # 删除QRCode文件
        if os.path.exists(self.VPath):
            os.remove(self.VPath)

        # 记录登陆账号的昵称
        tmpUserName = ret[11]

        html = self.Get(ret[5])
        url = getReValue(html, r' src="(.+?)"', 'Get mibao_res Url Error.', 0)
        if url != '':
            html = self.Get(url.replace('&amp;', '&'))
            url = getReValue(html, r'location\.href="(.+?)"', 'Get Redirect Url Error', 1)
            html = self.Get(url)

        PTWebQQ = self.getCookie('ptwebqq')

        logging.info('PTWebQQ: {0}'.format(PTWebQQ))

        LoginError = 1
        while LoginError > 0:
            try:
                html = self.Post('http://d.web2.qq.com/channel/login2', {
                    'r': '{{"ptwebqq":"{0}","clientid":{1},"psessionid":"{2}","status":"online"}}'.format(PTWebQQ, ClientID, PSessionID)
                }, Referer)
                ret = json.loads(html)
                LoginError = 0
            except:
                LoginError += 1
                logging.critical("登录失败，正在重试")

        if ret['retcode'] != 0:
            return

        VFWebQQ = ret['result']['vfwebqq']
        PSessionID = ret['result']['psessionid']

        logging.critical("QQ号：{0} 登陆成功, 用户名：{1}".format(ret['result']['uin'], tmpUserName))
        logging.info('Login success')
        logging.critical("登陆二维码用时" + pass_time() + "秒")

        msgId = int(random.uniform(20000, 50000))


class check_msg(threading.Thread):
    # try:
    #   pass
    # except KeybordInterrupt:
    #   try:
    #     user_input = (raw_input("回复系统：（输入格式:{群聊2or私聊1}, {群号or账号}, {内容}）\n")).split(",")
    #     if (user_input[0] == 1):

    #       for kv in self.FriendList :
    #         if str(kv[1]) == str(user_input[1]):
    #           tuin == kv[0]

    #       self.send_msg(tuin, user_input[2])

    #   except KeybordInterrupt:
    #     exit(0)
    #   except Exception, e:
    #     print Exception, e

    def __init__(self):
        threading.Thread.__init__(self)

    def run(self):
        global PTWebQQ
        E = 0
        # 心跳包轮询
        while 1:
            if E > 5:
                break
            try:
                ret = self.check()
            except:
                E += 1
                continue
            # logging.info(ret)

            # 返回数据有误
            if ret == "":
                E += 1
                continue

            # POST数据有误
            if ret['retcode'] == 100006:
                break

            # 无消息
            if ret['retcode'] == 102:
                E = 0
                continue

            # 更新PTWebQQ值
            if ret['retcode'] == 116:
                PTWebQQ = ret['p']
                E = 0
                continue

            if ret['retcode'] == 0:
                # 信息分发
                msg_handler(ret['result'])
                E = 0
                continue

        logging.critical("轮询错误超过五次")

    # 向服务器查询新消息
    def check(self):

        html = HttpClient_Ist.Post('http://d.web2.qq.com/channel/poll2', {
            'r': '{{"ptwebqq":"{1}","clientid":{2},"psessionid":"{0}","key":""}}'.format(PSessionID, PTWebQQ, ClientID)
        }, Referer)
        logging.info("Check html: " + str(html))
        try:
            ret = json.loads(html)
        except Exception as e:
            logging.error(e)
            logging.critical("Check error occured, retrying.")
            return self.check()

        return ret


class pmchat_thread(threading.Thread):

    
    # con = threading.Condition()
    stage = 0
    # newIp = ''

    def __init__(self, tuin):
        threading.Thread.__init__(self)
        self.tuin = tuin
        self.tqq = uin_to_account(tuin)
        
        stage = 0

    def run(self):
        while 1:
            self.stage = 0
            time.sleep(1800)

    def reply(self, content):
        send_msg(self.tuin, str(content))
        logging.info("Reply to " + str(self.tqq) + ":" + str(content))

    def push(self, ipContent):
        try:
            logging.info("PM get info from AI: "+ipContent)
            paraf={ 'userid' : str(self.tqq), 'key' : tulingkey, 'info' : ipContent}
            info = json.loads(HttpClient_Ist.Get('http://www.tuling123.com/openapi/api?'+urllib.urlencode(paraf)))
            if info["code"] in {40001, 40003, 40004}:
                self.reply("我今天累了，不聊了")
                logging.warning("Reach max AI call")
            elif info["code"] in {40002, 40005, 40006, 40007}:
                self.reply("我遇到了一点问题，请稍后@我")
                logging.warning("PM AI return error, code:"+str(info["code"]))
            else:
                self.reply(info["text"])
                logging.info("PM AI reply: "+str(info["text"]))
            return True
        except Exception, e:
            logging.error("ERROR:"+str(e))
        return False
        


class group_thread(threading.Thread):
    last1 = ''
    lastseq = 0
    replyList = {}
    followList = []

    # 属性
    repeatPicture = False

    def __init__(self, guin):
        threading.Thread.__init__(self)
        self.guin = guin
        self.gid = GroupList[guin]
        self.load()

    def learn(self, key, value, needreply=True):
        if key in self.replyList:
            self.replyList[key].append(value)
        else:
            self.replyList[key] = [value]

        if needreply:
            self.reply("我记住" + str(key) + "的回复了")
            self.save()

    def delete(self, key, value, needreply=True):
        if key in self.replyList and self.replyList[key].count(value):
            self.replyList[key].remove(value)
            if needreply:
                self.reply("我已经不会说" + str(value) + "了")
                self.save()

        else:
            if needreply:
                self.reply("没找到你说的那句话哦")

    def reply(self, content):
        reqURL = "http://d.web2.qq.com/channel/send_qun_msg2"
        data = (
            ('r', '{{"group_uin":{0}, "face":564,"content":"[\\"{4}\\",[\\"font\\",{{\\"name\\":\\"Arial\\",\\"size\\":\\"10\\",\\"style\\":[0,0,0],\\"color\\":\\"000000\\"}}]]","clientid":"{1}","msg_id":{2},"psessionid":"{3}"}}'.format(self.guin, ClientID, msgId, PSessionID, content.replace("\\", "\\\\\\\\"))),
            ('clientid', ClientID),
            ('psessionid', PSessionID)
        )
        logging.info("Reply package: " + str(data))
        rsp = HttpClient_Ist.Post(reqURL, data, Referer)
        if rsp:
            
            logging.info("[Reply to group " + str(self.gid) + "]:" + str(content))
        return rsp

    def handle(self, send_uin, content, seq):
        # 避免重复处理相同信息
        if seq != self.lastseq:
            pattern = re.compile(r'^(?:!|！)(learn|delete) {(.+)}{(.+)}')
            match = pattern.match(content)
            if match:
                if match.group(1) == 'learn':
                    self.learn(str(match.group(2)).decode('UTF-8'), str(match.group(3)).decode('UTF-8'))
                    logging.debug(self.replyList)
                if match.group(1) == 'delete':
                    self.delete(str(match.group(2)).decode('UTF-8'), str(match.group(3)).decode('UTF-8'))
                    logging.debug(self.replyList)

            else:
                # if not self.follow(send_uin, content):
                #     if not self.tucao(content):
                #         if not self.repeat(content):
                #             if not self.callout(content):
                #                 pass
                if self.callout(send_uin, content):
                    return
                if self.follow(send_uin, content):
                    return
                if self.tucao(content):
                    return
                if self.repeat(content):
                    return
                
        else:
            logging.warning("message seq repeat detected.")
        self.lastseq = seq

    def tucao(self, content):
        for key in self.replyList:
            if str(key) in content and self.replyList[key]:
                rd = random.randint(0, len(self.replyList[key]) - 1)
                self.reply(self.replyList[key][rd])
                logging.info('Group Reply'+str(self.replyList[key][rd]))
                return True
        return False

    def repeat(self, content):
        if self.last1 == str(content) and content != '' and content != ' ':
            if self.repeatPicture or "[图片]" not in content:
                self.reply(content)
                logging.info("已复读：{" + str(content) + "}")
                return True
        self.last1 = content
        
        return False

    def follow(self, send_uin, content):
        pattern = re.compile(r'^(?:!|！)(follow|unfollow) (\d+|me)')
        match = pattern.match(content)

        if match:
            target = str(match.group(2))
            if target == 'me':
                target = str(uin_to_account(send_uin))

            if match.group(1) == 'follow' and target not in self.followList:
                self.followList.append(target)
                self.reply("正在关注" + target)
                return True
            if match.group(1) == 'unfollow' and target in self.followList:
                self.followList.remove(target)
                self.reply("我不关注" + target + "了！")
                return True
        else:
            if str(uin_to_account(send_uin)) in self.followList:
                self.reply(content)
                return True
        return False

    def save(self):
        with open("database.save", "w+") as savefile:
            savefile.write(json.dumps(self.replyList))

    def load(self):
        try:
            with open("database.save", "r") as savefile:
                saves = savefile.read()
                if saves:
                    self.replyList = json.loads(saves)
        except Exception, e:
            logging.info("读取存档出错:"+str(e))

    def callout(self, send_uin, content):
        pattern = re.compile(r'^(?:!|！)(ai) (.+)') 
        match = pattern.match(content)
        try:
            if match:
                logging.info("get info from AI: "+str(match.group(2)).decode('UTF-8'))
                usr = str(uin_to_account(send_uin))
                paraf={ 'userid' : usr+'g', 'key' : tulingkey, 'info' : str(match.group(2)).decode('UTF-8')}
                
                info = json.loads(HttpClient_Ist.Get('http://www.tuling123.com/openapi/api?'+urllib.urlencode(paraf)))
                if info["code"] in {40001, 40003, 40004}:
                    self.reply("我今天累了，不聊了")
                    logging.warning("Reach max AI call")
                elif info["code"] in {40002, 40005, 40006, 40007}:
                    self.reply("我遇到了一点问题，请稍后@我")
                    logging.warning("AI return error, code:"+str(info["code"]))
                else:
                    self.reply(info["text"])
                    logging.info("AI reply: "+str(info["text"]))
                return True
        except Exception, e:
            logging.error("ERROR"+str(e))
        return False


# -----------------
# 主程序
# -----------------

if __name__ == "__main__":
    vpath = './v.jpg'
    qq = 0
    if len(sys.argv) > 1:
        vpath = sys.argv[1]
    if len(sys.argv) > 2:
        qq = sys.argv[2]

    try:
        pass_time()
        qqLogin = Login(vpath, qq)
    except Exception, e:
        logging.error(str(e))
    
    t_check = check_msg()
    t_check.setDaemon(True)
    t_check.start()
    try:        
        with open('groupfollow.txt','r') as f:
            for line in f:
                GroupWatchList += line.strip('\n').split(',')
            logging.info("关注:"+str(GroupWatchList))
    except Exception, e:
        logging.error("读取组存档出错:"+str(e))
            
                
    while 1:
        if not t_check.isAlive():
            exit(0)
