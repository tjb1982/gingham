import json, sys, requests

def deep_merger( new_settings, api_base, lcm_cluster_name):
    #new_setting is the json string to update the config file
    #api_base is the http://XX.XX.XXXX:8888/api/v1/lcm/ for the opscenter node
    #lcm_cluster_name is the name of cluster who's config profile we will copy and update

    #step 1: get the config profile
    # first find the ID for the cluster to get the correct config_profile
    clusters = requests.get(api_base+'clusters/').text
    cluster_list = json.loads(clusters)["results"]
    for cl in cluster_list:
        if cl["name"] == lcm_cluster_name:
            config_id = cl["config-profile-id"]
        #error, name is wrong TODO
        config_id = 0

    #step 2 :getting the json of the old config
    config_p = requests.get(api_base+'config_profile/'+config_id).text
    config_json = json.loads(config_p)["json"] # this is a dict object when returned

    #step 3: deep merge the two jsons
        #new_settings ex : '{"json": {"cassandra-yaml": {"start-native-transport": "True"},
        #                              "logback-xml": {"file-appender-min-index": 2,
        #                               "loggers": [{"name": "com.thinkaurelius.thrift",
        #                                            "level": "ERROR"}]} } }'
    merge(config_json, new_settings)


    #step 4: send out job to configure


###Function outputs an array from the combination of two arrays, whether they are in
# list or in dict format does not matter. However dicts must have keys that are only ints to index.
# old_array -> array that will be getting things merged into it; could be a list or dict
# new_array -> array that will overwrite if needed, merging into the old_array; could be a list or dict
# output -> list: should be populated with the desired new and old values, might also contain
# some Nones if the new array had things indexed at a higher value, like JS
def array_merge(old_array, new_array):

    #cases:
    #1 both are arrays
        #find largest index, iterate until that, make new array with both
    if isinstance(old_array,list) and isinstance(new_array, list):
        if len(old_array) <= len(new_array):
            out_array = new_array
        else:
            out_array = old_array
            for i in range(0, len(new_array)):
                out_array[i] = new_array[i]


    #2 first is array other is dict
        #find largest index, could be the array or could be the dict's max key list
        #make new array of largest index, fill with old array then new values or None
    elif ( isinstance(old_array, list) and isinstance(new_array, dict) ) or (isinstance(old_array, dict) and isinstance(new_array, list) ):

        if isinstance( old_array, list):
            dicti = new_array
            listi = old_array
        else:
            dicti = old_array
            listi = new_array


        na_max = max(dicti.keys())


        if  isinstance(na_max, int):
            if na_max+1 > len(listi): #most annoying case here
                out_array = [None] * (na_max +1)

                if dicti == new_array:
                    #means that it should populate after list
                    for i in range(0, len(listi)):
                        out_array[i] = listi[i]
                    for key in dicti:
                        out_array[key] = dicti[key]
                else:
                    for key in dicti:
                        out_array[key] = dicti[key]
                    for i in range(0, len(listi)):
                        out_array[i] = listi[i]

            else:
                if dicti == new_array:
                    out_array = listi
                    for key in dicti:
                        out_array[key] = dicti[key]
                else:
                    out_array = listi


        else: #any string or char for a key would be greater than an int so error
            raise IndexError("DICT WAS NOT INDEXABLE, sounds made up I know ")

    #3 both are dicts
        #make sure that all DICTs are indexed by ints otherwise exceptions
    elif isinstance(old_array, dict) and isinstance(new_array, dict):
        old_max = max(old_array.keys())
        new_max = max(new_array.keys())
        if isinstance(old_max, int) and isinstance(new_max,int):
            out_array = [None] * (old_max + 1)  if old_max >= new_max else [None] * (new_max+1)

            for key in old_array:
                out_array[key] = old_array[key]
            for key in new_array:
                out_array[key] = new_array[key]
        else:
            raise IndexError("DICT DOES NOT HAVE CORRECT KEYS")
    else:
        raise Exception("WRONG TYPES, lists and dicts only")

    return out_array


def merge(a, b, path=None):
    "merges b into a"
    if path is None: path = []
    for key in b:
        if key in a:
            if isinstance(a[key], dict) and isinstance(b[key], dict):
                if isinstance(max(a[key].keys()), int) or isinstance(max(b[key].keys()), int):
                    out = array_merge(a[key],b[key])
                    a[key] = out
                else:
                    merge(a[key], b[key], path + [str(key)])
            elif a[key] == b[key]:
                pass # same leaf value
            else:
                if isinstance(a[key],list) or isinstance(b[key], list) or isinstance(a[key],dict) or isinstance(b[key],dict):
                    out =array_merge(a[key],b[key])
                    a[key] = out
                else:
                    a[key] = b[key]
        else:
            a[key] = b[key]
    return a


def test(result, erwt):
    print(result)
    assert(result == erwt)

if __name__ == '__main__':

    test(merge({"foo": {"bar": "baz"}}, {"foo": {"lala": 123}}),
         { "foo" : { "bar": "baz", "lala": 123 } })
    test(merge({"foo": {"bar": "baz"}}, {"foo": {"bar": 123}}),
         { "foo" : { "bar": 123 } })
    test(merge({"foo": {"bar": ["baz"]}}, {"foo": {"bar": ["quux"]}}),
         { "foo" : { "bar": ["quux"] } })
    test(merge({"foo": {"bar": ["baz", "quux"]}}, {"foo": {"bar": {1: "lala"}}}),
         { "foo" : { "bar": ["baz", "lala"] } })
    test(merge({"foo": {"bar": ["baz", "quux"]}}, {"foo": {"bar": {2: "lala"}}}),
        { "foo" : { "bar": ["baz", "quux", "lala"] } })
    test(merge({"foo": {"bar": ["baz", "quux"]}}, {"foo": {"bar": {3: "lala"}}}),
         { "foo" : { "bar": ["baz", "quux", None, "lala"] } })
    test(merge({"foo": {"bar": ["baz", "quux", "hello"]}}, {"foo": {"bar": ["one", "two"]}}),
         { "foo" : { "bar": ["one", "two", "hello"] } })
    test(merge({"foo": {"bar": {1: "baz", 3: "quux", 2: "hello"}}}, {"foo": {"bar": ["one", "two"]}}),
         { "foo" : { "bar": ["one", "two", "hello", "quux"] } })
    test(merge({"foo": {"bar": {-1: "baz", 3: "quux", 2: "hello"}}}, {"foo": {"bar": ["one", "two"]}}),
         {'foo': {'bar': ['one', 'two', 'hello', 'baz']}})
    sys.exit(0)
