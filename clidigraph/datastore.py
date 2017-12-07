

def get_tag(data, name):
    tag, = [t for t in data['tags'] if re.search(name, t)]
    return tag
