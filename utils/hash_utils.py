import hashlib
import json

def hash_item(item):
    item_fp = hashlib.sha256(json.dumps(item, sort_keys=True).encode()).hexdigest()
    return item_fp