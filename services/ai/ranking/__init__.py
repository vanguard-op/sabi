"""Discovery ranking (FEAT-004, MQ-002).

Ranks catalogue agencies and billers for a discovery query and returns them in
the shape the client consumes (C-010). The model only selects and orders records
the retrieval index already holds; a record that cannot be traced back to the
catalogue is dropped rather than shown (model-quality.md, MQ-002).
"""
