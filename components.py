from utils import truncate

class Response:
    def __init__(self, msg=None, embed=None, file=None):
        self._name = 'Response'
        self.msg = msg
        self.embed = embed
        self.file = file

    def format(self, *args, **kwargs):
        if not self.msg:
            raise ValueError('Response with no msg content cannot be '
                             'formatted.')
        self.msg = self.msg.format(*args, **kwargs)
        return self.msg

    def __bool__(self):
        return any(self.msg, self.embed, self.file)

    def __repr__(self):
        r = self._name
        attachments = [self.embed and 'embed', self.file and 'file']
        if any(attachments):
            r += (' with ' + ' and '.join(attachments))
        if self.msg:
            r += f': {truncate(self.msg)}'
        return f'<{r}>'


class EmptyResponse(Response):
    def __init__(self):
        super().__init__(self)
        self._name = 'EmptyResponse'