from flask import Flask, Response, request, send_file
from repos.resolve import get_repo
import yaml
import re

app = Flask(__name__)

package_pattern = \
    re.compile(r'^(.*)-((0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-(0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)'
               r'(\.(0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*)?(\+[0-9a-zA-Z-]+(\.[0-9a-zA-Z-]+)*)?)$')

def credentials(request):
    return request.authorization


@app.route('/<path:repo>/index.yaml')
def get_index(repo):
    root = request.headers['Host']
    return as_yaml(get_repo(repo, root, credentials(request)).generate_index())


@app.route('/<path:repo>/charts/<path:package>.tgz')
def get_package(repo: str, package: str):
    root = request.headers['Host']
    matcher = package_pattern.match(package)
    if not matcher:
        return Response(status=404)
    name = matcher.group(1)
    version = matcher.group(2)
    return send_file(get_repo(repo, root, credentials(request)).fetch(name, version),
              mimetype='application/tar+gzip')


def as_yaml(dict, status=200, headers={}):
    return Response(yaml.dump(dict), content_type='text/yaml', status=status, headers=headers)


if __name__ == '__main__':
    app.run()
