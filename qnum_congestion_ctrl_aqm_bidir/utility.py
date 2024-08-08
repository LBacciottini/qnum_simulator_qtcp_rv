
def sanitize_flow_descriptors(flow_descriptors):
    """
    Sanitize the flow_descriptors parameter, transforming it into a dictionary indexed by flow_id
    """
    if isinstance(flow_descriptors, list):
        flow_descriptors_dict = {}
        for flow_descriptor in flow_descriptors:
            flow_descriptors_dict[flow_descriptor['flow_id']] = flow_descriptor
    elif isinstance(flow_descriptors, dict):
        flow_descriptors_dict = flow_descriptors
    else:
        raise ValueError("flow_descriptors must be a list or a dictionary")

    # check if the dictionary is well-formed
    for flow_id, flow_descriptor in flow_descriptors_dict.items():
        if 'flow_id' not in flow_descriptor:
            raise ValueError("flow_descriptor must contain a flow_id key")
        elif flow_descriptor['flow_id'] != flow_id:
            raise ValueError("flow_id in flow_descriptor does not match the key in the dictionary")

    return list(flow_descriptors_dict.values())
