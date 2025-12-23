# src/controller/of_db.py

class SRTEntry:
    """
    Represents one SRT entry (Eq. 2 in paper)
    SRT = { P_ai, {S_ai,k}, F_i^TS }
    """
    def __init__(self, publisher, subscribers, rt_props, path):
        self.publisher = publisher
        self.subscribers = subscribers
        self.rt_props = rt_props
        self.path = path


class OFDatabase:
    """
    Software emulation of OF-DB (Section 4.2)
    """
    def __init__(self):
        self.srt_table = []

    def exists(self, publisher, rt_props):
        for entry in self.srt_table:
            if entry.publisher == publisher and entry.rt_props == rt_props:
                return True
        return False

    def add_entry(self, publisher, subscribers, rt_props, path):
        entry = SRTEntry(publisher, subscribers, rt_props, path)
        self.srt_table.append(entry)

    def get_all(self):
        return self.srt_table

    def remove_entry(self, publisher, subscribers):
        self.srt_table = [e for e in self.srt_table 
                          if not (e.publisher == publisher and e.subscribers == subscribers)]
