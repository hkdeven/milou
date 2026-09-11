from .models import SourceDefinition


SOURCES = (
    SourceDefinition("Rest of World", "https://restofworld.org/", "Global South", "impact"),
    SourceDefinition("MIT Technology Review", "https://www.technologyreview.com/topic/artificial-intelligence/", "North America/Europe", "technical", False),
    SourceDefinition("IEEE Spectrum", "https://spectrum.ieee.org/topic/artificial-intelligence/", "North America/Europe", "technical", False),
    SourceDefinition("THE DECODER", "https://the-decoder.com/", "Europe", "technical"),
    SourceDefinition("South China Morning Post", "https://www.scmp.com/tech", "East Asia", "regional-business"),
    SourceDefinition("Euractiv", "https://www.euractiv.com/topics/artificial-intelligence/", "Europe", "policy"),
    SourceDefinition("TechCrunch", "https://techcrunch.com/category/artificial-intelligence/", "North America", "business", False),
    SourceDefinition("Nikkei Asia", "https://asia.nikkei.com/Business/Technology", "Asia-Pacific", "business"),
)
