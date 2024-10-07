from sample import SampleModule, SampleTrigger

if __name__ == "__main__":
    module = SampleModule()
    module.register(SampleTrigger, "alert_created_trigger")
    module.register(SampleTrigger, "request")
    module.register(SampleTrigger, "connector")
    module.run()
