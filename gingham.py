#!/usr/bin/env python

from __future__ import print_function
import sys, os, json, requests, operator, yaml, time, copy
from merge import merge


headers = {'Content-Type': 'application/json'}
genv = {}

def verify(erwt, body, reports = None, depth = 0, parent_key = None, optional = False, local_env = None, throw = False):

    reports = reports if reports is not None else [[],[]]
    local_env = local_env if local_env is not None else {}
    env = local_env.copy()

    env.update(genv)

    def append_report(optional, report):
        if optional:
           reports[0].append(report)
        else:
           reports[1].append(report)

    if type(erwt) == dict:

        for key in erwt:

            if type(key) == int:
                if len(body) <= key:
                    append_report(optional, (
                        "The item at index %s doesn't exist for key '%s' at depth %s"
                    ) % (key, parent_key, depth - 1))
                else:
                    throw = verify(erwt[key], body[key], reports, depth + 1, key, optional, local_env, throw)[2]

            else:

                parts = key.split("?")
                body_key = parts[0]
                opt = optional or len(parts) > 1

                if ~key.find('$$$'):
                    if '$type' in key:
                        erwt_type = getattr(__builtins__, evaluate(erwt[key], None, env))
                        body_type = type(body)
    
                        if erwt_type != body_type:
                            append_report(opt, (
                                "The type for the value of key '%s' at depth %s was expected to be '%s', but was %s instead"
                            ) % (key, depth, erwt_type, body_type))

                    elif '$value' in key:
                        value = evaluate(erwt[key], None, env)
                        if value != body:
                            append_report(opt, (
                                "The value for key '%s' at depth %s was expected to be %s (%s), but was %s (%s) instead"
                            ) % (parent_key, depth, value, type(value), body, type(body)))

                    elif '$ops' in key:
                        operators = erwt[key]
                        for op in operators:
                            value = evaluate(erwt[key][op], None, env)
                            if not getattr(operator, op)(body, value):
                                append_report(opt, (
                                    "The value for key '%s' at depth %s was expected to be %s %s (%s), but was %s (%s) instead"
                                ) % (parent_key, depth, op, value, type(value), body, type(body)))

                    elif '$or' in key:
                        options = evaluate(erwt[key], None, env)
                        if body not in options:
                            append_report(opt, (
                                "The value for key '%s' at depth %s was expected to be one of %s, but was %s (%s) instead"
                            ) % (parent_key, depth, " or ".join(map(lambda x: "%s (%s)" % (x, type(x)), options)), body, type(body)))

                    elif '$set' in key:
                        genv[interpolate(erwt[key], env)] = body

                    elif '$throw' in key:
                        value = evaluate(erwt[key], None, env)
                        if value == body:
                            throw = True
                            append_report(False, (
                                "The value for key '%s' at depth %s was expected NOT to be %s (%s), but it was"
                            ) % (parent_key, depth, value, type(value)))
                            return [reports, local_env, throw]

                    elif '$eval' in key:
                        def _eval(this, expected):
                            try:
                                exec erwt[key] in globals(), locals()
                            except Exception as e:
                                append_report(opt,
                                    " ".join(["$$$eval failed for key '{key}' at depth {depth}",
                                              "with arguments: {args}\n{exception}"]).format(
                                        key=key,
                                        depth=depth,
                                        args={"expected": expected, "this": this},
                                        exception=e
                                    ))
                        result = _eval(body, erwt)
                        if result == False:
                            append_report(opt,
                                " ".join(["$$$eval failed for key '{key}' at depth {depth}",
                                          "with arguments: {args}"]).format(
                                    key=key,
                                    depth=depth,
                                    args={"expected": expected, "actual": actual}
                                ))

                    elif '$log' in key:
                        print(erwt[key] % body, file=sys.stderr)

                    elif '$let' in key:
                        letargs = [[erwt[key], body], {'$$$identity': body}]
                        local_env[erwt[key]] = evaluate({key: letargs}, None, env)
                        #local_env[erwt[key]] = body
    
                elif not opt and key not in body:
                    append_report(opt, (
                        "Key '%s' not found in response at depth %s"
                    ) % (key, depth))

                else:
                    throw = verify(erwt[key], body.get(body_key), reports, depth + 1, key, opt, local_env, throw)[2]

    return [reports, local_env, throw]


def redact(data, redacted = []):
    data_cp = copy.deepcopy(data) if data else None
    if data_cp:
        for key in redacted:
            if data_cp.get(key):
                data_cp[key] = "REDACTED"
    return data_cp


def compare_status_dict(endpoint, t, idx, env = None):

    env = env.copy() if env is not None else {}
    data = t.get('data')
    redacted = data.pop("$$$redacted", []) if data else []
    redacted_data = redact(data, redacted)
    verif = t.get('verify', False)

    #print("Test #%s. %s\n%s %s" % (idx, interpolate(t.get('description'), env) or '', t.get('method').upper(), endpoint), file=sys.stderr)
    print("%s %s" % (t.get('method').upper(), endpoint), file=sys.stderr)
    if redacted_data:

        print('\tpayload: %s' % json.dumps(redacted_data), file=sys.stderr)
        print('\tverify: %s' % verif, file=sys.stderr)

    def check(attempts_remaining = 0):

        if '$$$delay' in t:
            time.sleep(float(swap(evaluate(t.get('$$$delay'), None, env))) / 1000)

        s = getattr(requests, t['method'])(
            endpoint,
            data = json.dumps(data),
            verify=verif,
            headers=headers,
            timeout=60.0
        )

        okay = True
        warn = False
        body_reports = [[],[]]
        header_reports = [[],[]]
        status_reports = [[],[]]
        throw = False

        for k in t:
            optional = '?' in k
            if 'status' in k:
                status_reports, e, throw = verify(t[k], s.status_code, optional=optional, parent_key='status', local_env=env)
                okay = okay and not len(status_reports[1])
                warn = warn or len(status_reports[0])
                attempts_remaining = attempts_remaining if not throw else 0
            elif 'body' in k:
                try:
                    body_reports, e, throw = verify(t[k], s.json(), optional=optional, local_env=env)
                except ValueError:
                    body_reports[1].append("Expected payload to be JSON\n\tGot %s instead." % s.text)
                okay = okay and not len(body_reports[1])
                warn = warn or len(body_reports[0])
                attempts_remaining = attempts_remaining if not throw else 0
            elif 'headers' in k:
                header_reports, e, throw = verify(t[k], s.headers, optional=optional, local_env=env)
                okay = okay and not len(header_reports[1])
                warn = warn or len(header_reports[0])
                attempts_remaining = attempts_remaining if not throw else 0

        if not okay:
            if attempts_remaining > 0:
                sys.stderr.write('.')
                sys.stderr.flush()
                return check(attempts_remaining - 1)
            print(
                "Failed: %s\n%s %s %s" % (
                    interpolate(t.get('expectation')) if t.get('expectation') else "",
                    "\tStatus errors:\n\t\t%s\n" % ", \n\t\t".join(status_reports[1]) if status_reports[1] else "",
                    "\tBody errors:\n\t\t%s\n" % ", \n\t\t".join(body_reports[1]) if body_reports[1] else "",
                    "\tHeader errors:\n\t\t%s\n" % ", \n\t\t".join(header_reports[1]) if header_reports[1] else ""
                ),
                file=sys.stderr
            )
            print(
                "%s %s %s %s" % (
                    "\n\tdata:\n\t\t%s\n" % redacted_data if redacted_data else "",
                    "\n\tbody:\n\t\t%s\n" % s.content if s.content else "",
                    "\n\theaders:\n\t\t%s\n" % s.headers if s.headers else "",
                    "\n\treason:\n\t\t%s\n" % s.reason if s.reason and s.reason != "OK" else ""
                ),
                file=sys.stderr
            )
        else:
            if warn:
                print(
                    "Warning:\n%s %s %s" % (
                        "\tStatus:\n\t\t%s\n" % ", \n\t\t".join(status_reports[0]) if status_reports[0] else "",
                        "\tBody:\n\t\t%s\n" % ", \n\t\t".join(body_reports[0]) if body_reports[0] else "",
                        "\tHeader:\n\t\t%s\n" % ", \n\t\t".join(header_reports[0]) if header_reports[0] else ""
                ),
                file=sys.stderr)

            if '$$$then' in t:
                print("", file=sys.stderr)
                for endpoints in t.get('$$$then'):
                    for context in endpoints:
                        endp = expand_endpoint(context, env)
                        print("%sthen ==> " % (
                                "".join(map(lambda x: "\t" if x > 0 else "", range(0, len(str(idx).split(".")))))
                            ),
                            file=sys.stderr
                        )
                        for result in [compare_status_dict(endp, tt, "%s.%s" % (idx, i + 1), env) for i, tt in enumerate(endpoints[context])]:
                            okay = okay and result
                return okay
            else:
                print("OK\n", file=sys.stderr)

        return okay

    return check(float(evaluate(t.get('$$$retry'), None, env)) if t.get('$$$retry') else 0)


def interpolate(string, env = None):
    env = env.copy() if env is not None else {}
    env.update(genv)
    try:
        return string.format(**env)
    except KeyError:
        pass
    except AttributeError:
        pass
    return string


def maybe_to_number(expr):
    if type(expr) is not str: return expr
    try:
        return int(expr)
    except ValueError:
        try:
            return float(expr)
        except ValueError:
            return expr


def swap(k, env = None):
    env = env.copy() if env is not None else {}
    env.update(genv)

    if type(k) is str and k.strip().startswith("<"):
        _, filename = k.split("<")
        with open(swap(filename.strip(), env), 'r') as f:
            ret = f.read().strip()
        return ret

    try:
        return maybe_to_number(env[k])
    except KeyError:
        try:
            return maybe_to_number(("{%s}" % k).format(**env))
        except IndexError:
            pass
        except KeyError:
            pass
    except TypeError:
        pass

    if type(k) is str:
       k = interpolate(k, env)

    return k


def expand_endpoint(context = "", env = {}):
    if context[0:1] == "/":
        return "%s%s" % (api_base, interpolate(context, env))
    else:
        return interpolate(context, env)


def evaluate(form, results, env = None, allow_endpoint = True):

    env = env.copy() if env is not None else {}

    if type(form) is dict:
        if not allow_endpoint:
            for k in form:
                v = evaluate(form[k], results, env, allow_endpoint)
                form[evaluate(k, results, env, allow_endpoint)] = v
            return form
        for function in form:
            name = function
            args = form[function]

            if '$$$' in name:
                if '$let' in name or '$set' in name:
                    xenv = genv if '$set' in name else env
                    for i in range(0, len(args[0]), 2):
                        if type(args[0][i]) is list:
                            parts = evaluate(args[0][i+1], results, env)
                            for idx, part in enumerate(parts):
                                xenv[args[0][i][idx]] = part
                        else:
                            xenv[args[0][i]] = evaluate(args[0][i+1], results, env)
                    ret = None
                    if len(args) > 1:
                        for expr in args[1:]:
                            ret = evaluate(expr, results, env)
                    return ret
                elif '$assoc' in name:
                    subj = copy.deepcopy(evaluate(args[0], results, env, allow_endpoint))
                    subj[args[1]] = args[2]
                    return subj
                elif '$select-keys' in name:
                    subj = copy.deepcopy(evaluate(args[0], results, env, allow_endpoint))
                    new_map = {}
                    for k in subj:
                        if subj[k] in args[1:]:
                            new_map[k] = subj[k]
                    return new_map
                elif '$merge' in name:
                    #new_map = copy.deepcopy(evaluate(args[0], results, env, allow_endpoint))
                    #for k in args[1]:
                    #    new_map[k] = args[1][k]
                    #return new_map
                ##########
                    old_map = copy.deepcopy(evaluate(args[0], results, env, allow_endpoint=False))
                    new_map = copy.deepcopy(evaluate(args[1], results, env, allow_endpoint=False))
                    return merge(old_map, new_map)
                elif '$split' in name:
                    return apply(str.split, evaluate(args, results, env))
                elif '$range' in name:
                    return apply(range, evaluate(args, results, env))
                elif '$len' in name:
                    return len(evaluate(args, results, env))
                elif '$get' in name:
                    ret = evaluate(args[0], results, env)
                    for key in args[1:]:
                        ret = ret.__getitem__(evaluate(key, results, env))
                    return ret
                    #return evaluate(args[0], results, env).__getitem__(evaluate(args[1], results, env))
                elif '$sum' in name:
                    return sum(evaluate(args, results, env))
                elif '$product' in name:
                    return reduce(operator.mul, evaluate(args, results, env))
                elif '$if' in name:
                    if evaluate(args[0], results, env):
                        return evaluate(args[1], results, env)
                    elif len(args) > 2:
                        return evaluate(args[2], results, env)
                    #return evaluate(args[1], results, env) if evaluate(args[0], results, env) else evaluate(args[2], results, env)
                elif '$eq' in name:
                    return reduce(operator.eq, evaluate(args, results, env))
                elif '$type' in name:
                    return str(type(evaluate(args, results, env)))
                elif '$identity' in name:
                    return evaluate(args, results, env, allow_endpoint = False)
                elif '$log' in name:
                    value = evaluate(args, results, env)
                    print(value, file=sys.stderr)
                    return value
                elif '$run' in name:
                    return [run(evaluate(arg, results, env), results, env) for arg in evaluate(args, results, env)]
                elif '$for' in name:
                    newlist = []
                    for var in evaluate(args[0][1], results, env):
                        argsc = copy.deepcopy(args[1])
                        env[args[0][0]] = var
                        newlist.append(evaluate(argsc, results, env))
                    return newlist
            else:
                endpoint = expand_endpoint(name, env)
                #print("%s %s:" % (args[0].get('method').upper(), endpoint), file=sys.stderr)
                for idx, t in enumerate(args):
                    t['data'] = evaluate(t.get('data'), results, env, allow_endpoint = False)
                    results.append([
                        compare_status_dict(
                            endpoint, t, "%s.%s" % (len(results) + 1, idx + 1), env
                        )
                    ])
                return None
    elif type(form) is list:
        return map(lambda x: evaluate(x, results, env, allow_endpoint), form)
    else:
        return swap(form, env)

def run(test_file, results, env):

    if not test_file:
        f = sys.stdin
    else:
        f = open(test_file, 'r')

    docs = yaml.load_all(f)
    for doc in docs:
        for functions in doc:
            evaluate(functions, results, env)

    if test_file:
        f.close()

    return results

if __name__ == '__main__':

    api_base = ""
    test_file = None

    genv["argv"] = []
    if len(sys.argv) == 2:
        test_file = sys.argv[1]
    else:
        for i in range(1, len(sys.argv[1:]) + 1):
            if sys.argv[i] == "-b" and len(sys.argv) > i + 1:
                api_base = sys.argv[i + 1]
            elif sys.argv[i] == "-a" and len(sys.argv) > i + 1:
                key, _, val = sys.argv[i + 1].partition('=')
                genv[key] = val
            elif sys.argv[i] == "-t" and len(sys.argv) > i + 1:
                test_file = sys.argv[i + 1]

    try:
        for arg in sys.argv[sys.argv.index("--") + 1:]:
            genv["argv"].append(arg)
    except ValueError:
        pass

#    print(genv)
#    sys.exit(0)

    results = []
    env = {}

    results = run(test_file, results, env)
#    with open(test_file, 'r') as f:
#        docs = yaml.load_all(f)
#        for doc in docs:
#            for functions in doc:
#                evaluate(functions, results, env)

    passed = True
    passing = 0
    failing = 0

    for tests in results:
        for result in tests:
            passing += result and True
            failing += not result and True
            passed = passed and result

    print("%s passing." % passing, file=sys.stderr)
    print("%s failing." % failing, file=sys.stderr)

    print("\nEnvironment: %s" % genv, file=sys.stderr)

    if passed:
        print("OK\n")

    sys.exit(not passed)

