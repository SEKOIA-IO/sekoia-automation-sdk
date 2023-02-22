from {{cookiecutter.module_name.lower()}}_modules import {{cookiecutter.module_name.capitalize()}}Module

if __name__ == "__main__":
    module = {{cookiecutter.module_name.title().replace(" ", "")}}Module()
    module.run()
