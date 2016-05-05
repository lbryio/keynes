import json
import cleverbot

from datetime import datetime
from slackclient import SlackClient
from jsonrpc.proxy import JSONRPCProxy
from lbrynet.conf import API_CONNECTION_STRING

from twisted.internet import reactor, defer
from twisted.internet.task import LoopingCall
from twisted.internet import defer


class Autofetcher(object):
    def __init__(self):
        self._api = JSONRPCProxy.from_url(API_CONNECTION_STRING)
        self._checker = LoopingCall(self._check_for_new_claims)
        self.best_block = None

    def start(self):
        self._checker.start(5)

    def _check_for_new_claims(self):
        block = self._api.get_best_blockhash()
        if block != self.best_block:
            print "Checking new block for name claims, block hash: " + block
            self.best_block = block
            transactions = self._api.get_block({'blockhash': block})['tx']
            for t in transactions:
                c = self._api.get_claims_for_tx({'txid': t})
                if len(c):
                    for i in c:
                        print "Getting claim for txid: " + t
                        print "Stream info: " + i['value']
                        self._api.get({'name': t, 'stream_info': json.loads(i['value'])})


class LBRYBot(object):
    def __init__(self):
        print 'Starting up'
        self._api = JSONRPCProxy.from_url(API_CONNECTION_STRING)
        self._restricted_api_functions = ['stop_lbry_file', 'start_lbry_file', 'delete_lbry_file',
                                          'set_settings', 'publish', 'get', 'stop',
                                          'send_amount_to_address', 'abandon_name']

        self._api_functions = [f for f in self._api.help() if f not in self._restricted_api_functions]
        self._cb = cleverbot.Cleverbot()
        self.sc = SlackClient('xoxb-18962700149-nd9s2Q0FPS866o6mArdqXkbk')

        self._fetcher = Autofetcher()

        self.channels = {}
        self.users = {}
        self.message_queue = []

        self.slackrx = LoopingCall(self._get_messages)

    def setup(self):
        self.sc.rtm_connect()
        for c in json.loads(self.sc.api_call('channels.list'))['channels']:
            self.channels[c['name']] = c['id']
        for u in json.loads(self.sc.api_call('users.list'))['members']:
            self.users[u['id']] = u['name']
        self._fetcher.start()
        self.slackrx.start(2.0)

    def _send_message(self, channel, msg):
        self.message_queue.reverse()
        self.message_queue.append((channel, msg))
        self.message_queue.reverse()
        return defer.succeed(None)

    def _send_queue(self):
        try:
            channel, msg = self.message_queue.pop()
            self.sc.rtm_send_message(channel, msg)
            print "Sent: " + msg + " to channel, " + channel
        except:
            print "Failed to send: " + msg + " to channel, " + channel + "... retrying..."
            self.message_queue.reverse()
            self.message_queue.append((channel, msg))
            self.message_queue.reverse()
            self.sc.rtm_connect()

    def _get_messages(self):
        def _handle(message):
            if 'type' in message.keys():
                try:
                    if message['type'] == 'message':
                        print "[" + str(datetime.now()) + "] " + message['text']
                        if str(message['text']).startswith("-&gt;"):
                            cmd = str(message['text'])[5:]
                            if message['user'] == "U0C1MPSV7":
                                func = cmd.split(' ')[0]
                                params = {}
                                for a in cmd.split(' ')[1:]:
                                    v = a.split("=")[1]
                                    try:
                                        v = float(v)
                                    except:
                                        v = a.split("=")[1]
                                    params[a.split("=")[0]] = v
                                print "run (for jack) " + func + "(" + str(params) + ")"
                                r = self._api.call(func, params)
                                if isinstance(r, list):
                                    msg = ''
                                    for i in r:
                                        msg += str(i) + "\n"
                                    return self._send_message(message['channel'], msg)
                                elif isinstance(r, dict):
                                    msg = ''
                                    for i in r.keys():
                                        msg += i + ": " + str(r[i]) + "\n"
                                    return self._send_message(message['channel'], msg)
                                else:
                                    return self._send_message(message['channel'], str(r))
                            elif cmd.split(' ')[0] in self._api_functions:
                                func = cmd.split(' ')[0]
                                params = {}
                                for a in cmd.split(' ')[1:]:
                                    params[a.split("=")[0]] = a.split("=")[1]
                                print "run " + func + "(" + str(params) + ")"
                                r = self._api.call(func, params)
                                if isinstance(r, list):
                                    msg = ''
                                    for i in r:
                                        msg += str(i) + "\n"
                                    return self._send_message(message['channel'], msg)
                                elif isinstance(r, dict):
                                    msg = ''
                                    for i in r.keys():
                                        msg += i + ": " + str(r[i]) + "\n"
                                    return self._send_message(message['channel'], msg)
                                else:
                                    return self._send_message(message['channel'], str(r))
                            else:
                                return self._send_message(message['channel'], "unrecognized command")
                        elif "<@U0JUALL4D>:" in str(message['text']):
                            return self._send_message(message['channel'], str(self._cb.ask(str(message['text']).replace('<@U0JUALL4D>:', 'cleverbot'))).replace('cleverbot', '<@U0JUALL4D>:'))
                except Exception as err:
                    print 'Caught exception', err.message
            return defer.succeed(None)

        self.sc.rtm_connect()
        msgs = self.sc.rtm_read()
        if msgs:
            d = defer.DeferredList([_handle(m) for m in msgs if 'text' in m.keys()])
        else:
            d = defer.succeed(None)
        if len(self.message_queue):
            d.addCallback(lambda _: self._send_queue())

    def say(self, channel, msg):
        if channel in self.channels.keys():
            self.sc.rtm_send_message(self.channels[channel], msg)


def main():
    bot = LBRYBot()
    bot.setup()
    reactor.run()

if __name__ == '__main__':
    main()
