import json

class Link:
    def __init__(self, url, anchor, context):
        self.url = url
        self.anchor = anchor
        self.context = context
        self.score = None
        self.nlp = None

    def to_dict(self):
        return {
            "url": self.url,
            "anchor": self.anchor,
            "context": self.context
        }

    def to_json(self):
        return json.dumps(self.to_dict(), ensure_ascii=False)
 
    def get_url(self):
        return self.url