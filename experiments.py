dic1 = {'a':2, 'b':3}
dic2 = {'a':2, 'b':3}
result = {k: dic1.get(k) + dic2.get(k) for k in dic1.keys() | dic2.keys()}

print(result)