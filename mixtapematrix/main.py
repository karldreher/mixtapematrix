from .lib.router import File, FileRouter
import yaml


class MixtapeMatrix:
    def __init__(self, config: str):
        self.config = config
        self.config_data = self.load_config()

    def load_config(self):
        with open(self.config, 'r') as f:
            return yaml.safe_load(f)

    def run(self):
        # TODO: pydantic this thing
        for source in self.config_data.get('sources', []):
            print(f"Copying {source}")
            source_file = File(path=source.get('source_path'))
            destination_file = File(path=source.get('destination_path'))
            print(f"Destination: {destination_file.path}")
            for i in source.get('mp3_files', []):
                # TODO Make this more dynamic according to supported routers
                if i.get('artist'):
                    print(f"Artist: {i.get('artist')}")

            #     router = FileRouter.get_router(source_file, destination_file)
            #     router.deeply_copy(source_file, destination_file)

def main():
    matrix = MixtapeMatrix("router.yaml")
    matrix.run()
