class Storage:
    def __init__(self):
        self.nodes = []
        self.current_id = 0
        self.link_to_id={} # link -> id
        self.found_links = set()  
        self.domains  = {}  #base_url -> domain object

        self.items={} # hash -> item dict
    
    def get_node(self,id):
        return self.nodes[id]
    
    def add_domain(self,domain) : 
        base_url = domain.get_base_url()
        self.domains[base_url] = domain
    
    def get_domain(self,base_url):
        return self.domains[base_url]
    
    def add_node(self,node):
        self.nodes.append(node)
        self.found_links.add(node.get_link())
        self.link_to_id[node.get_link()] = node.get_id()

    def add_item(self,item,hash,parent):
        self.items[hash] = parent
        self.nodes[parent.get_id()].add_item(item,hash)

    def node_id_from_link(self,link):
        return self.link_to_id[link]

    def add_links(self,links):
        for link in links : 
            self.found_links.add(link.url)

    
    
    def next_id(self):
        self.current_id +=1
        return self.current_id-1

    def link_seen(self,link):
        return link in self.found_links
    def item_seen(self,hash):
        return hash in self.items