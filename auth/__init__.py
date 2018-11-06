import discord


class PrivilegeChecker:
    def __init__(self, client):
        self.priv_userids = {}
        self.priv_roleids = {}
        self.client = client

    def set_trust_for_userid(self, userid, to=True):
        try:
            self.client.get_user_info(userid)
        except discord.NotFound:
            msg = "invalid userid argument to add_userid()"
            raise ValueError(msg)
        except Exception as e:
            raise e
        self.priv_userids[userid] = bool(to)

    def set_trust_for_roleid(self, roleid, to=True):
        self.priv_roleids[roleid] = bool(to)

    def has_privilege(self, user):
        if not isinstance(discord.User, user):
            raise ValueError("has_trustlevel() expects a discord.User object "
                             "as the 'user' argument, not " + repr(user))
        
        if self.priv_userids.get(user.id):
            return True
        else:
            roles = getattr(user, 'roles', [])
            for role in roles:
                if self.priv_roleids.get(role.id):
                    return True

        return False
