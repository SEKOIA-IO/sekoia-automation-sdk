from sample import SampleModule

from sample import SampleTrigger
from sample import SampleAction


if __name__ == "__main__":
    module = SampleModule()
    module.register(SampleTrigger, "SampleTrigger")
    module.register(SampleAction, "SampleAction")
    module.run()
