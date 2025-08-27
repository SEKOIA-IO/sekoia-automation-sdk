from sample import SampleModule

from sample import SampleTrigger
from sample import SampleConnector
from sample import SampleAction


if __name__ == "__main__":
    module = SampleModule()
    module.register(SampleTrigger, "SampleTrigger")
    module.register(SampleConnector, "SampleConnector")
    module.register(SampleAction, "SampleAction")
    module.run()
