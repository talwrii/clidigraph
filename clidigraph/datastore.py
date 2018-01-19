
import re

def get_tag(data, tag):
    possible = [t for t in data['tags'] if re.search(tag, t)]
    try:
        result, = possible
    except:
        raise ValueError(tag)
    return result
