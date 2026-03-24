from sample import SampleAction, SampleConnector, SampleModule, SampleTrigger

if __name__ == "__main__":
    module = SampleModule()
    module.register(SampleTrigger, "SampleTrigger")
    module.register(SampleConnector, "SampleConnector")
    module.register(SampleAction, "SampleAction")
    module.run()
