
import re

def get_tag(data, name):
    possible = [t for t in data['tags'] if re.search(name, t)]
    try:
        tag, = possible
    except:
        raise ValueError(name)
    return tag
