from metal_libraries.utils.ci_info import CIInfo
class a:
    def __init__(self):
        self.a=CIInfo()
        pass
    def b(self):
        build=self.a.published_releases() 
        return build

        
print(a().b())
