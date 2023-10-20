from {{cookiecutter.module_name.lower().replace(" ", "_")}}_modules import {{cookiecutter.module_name.title().replace(" ", "")}}Module

if __name__ == "__main__":
    module = {{cookiecutter.module_name.title().replace(" ", "")}}Module()
    module.run()
