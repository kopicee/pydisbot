import asyncio
import json
import random

import discord

# Base58 to avoid ambiguous characters. Using the IPFS one.
BASE58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"

# Interval, in secs, to regenerate authcodes
AUTHCODE_REGEN_INTERVAL_SECS = 60 * 5

class PrivilegeChecker:
    def __init__(self, client, authfile_path):
        self.client = client
        self.file = authfile_path
        self.authcode = None

        self.privs = {
            'userids': {},
            'roleids': {}
        }
        try:
            with open(self.file, 'r', encoding='utf-8') as f:
                data = f.read()
                if data:
                    self.privs = json.loads(data)
        except FileNotFoundError:
            open(self.file, 'a', encoding='utf-8').close()
        except Exception as e:
            raise e
                

    def set_trust_for_userid(self, userid, authcode=None, to=True):
        try:
            self.client.get_user_info(userid)
        except discord.NotFound:
            msg = "invalid userid argument to add_userid()"
            raise ValueError(msg)
        except Exception as e:
            raise e
        
        if to == True:
            success = self.test_authcode(authcode)
            if not success:
                raise BadAuthCodeError

        self.privs['userids'][userid] = bool(to)
        self.commit()


    def set_trust_for_roleid(self, roleid, to=True):
        if to == True:
            success = self.test_authcode(authcode)
            if not success:
                raise BadAuthCodeError
        self.privs['roleids'][roleid] = bool(to)
        self.commit()


    def test_authcode(self, authcode):
        if authcode == self.authcode:
            self.regen_authcode()
            return True
        else:
            self.touch_authcode()
            return False


    def has_privilege(self, user):
        if not isinstance(user, discord.User):
            raise ValueError("has_trustlevel() expects a discord.User object "
                             "as the 'user' argument, not " + repr(user))
        
        if self.privs['userids'].get(user.id):
            return True
        else:
            roles = getattr(user, 'roles', [])
            for role in roles:
                if self.privs['roleids'].get(role.id):
                    return True
        return False


    def regen_authcode(self):
        self.authcode = ''.join(map(lambda _: random.choice(BASE58), '1234'))
        self.authcode_ttl = 3
        print('[auth] NEW AUTHCODE:', self.authcode)


    def touch_authcode(self):
        if not hasattr(self, 'authcode_ttl'):
            self.authcode_ttl = 0
        else:
            self.authcode_ttl -= 1    
        if self.authcode_ttl <= 0:
            self.regen_authcode()


    async def authcode_task(self, client):
        await client.wait_until_ready()
        await asyncio.sleep(5)
        while not client.is_closed:
            self.regen_authcode()
            await asyncio.sleep(max(AUTHCODE_REGEN_INTERVAL_SECS - 5, 0))


    def commit(self):
        with open(self.file, 'w', encoding='utf-8') as f:
            datas = json.dumps(self.privs)
            f.write(datas)


class BadAuthCodeError(Exception):
    def __init__(self):
        super().__init__(self)
