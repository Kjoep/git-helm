
class Repository:
    def generate_index(self) -> dict:
        raise NotImplementedError

    def fetch(self, name, version):
        raise NotImplementedError
