"""自写教学示例：缓存命中跳过计算；规则变化后清除旧值。"""

cache = {}
computations = 0


def square(n):
    global computations
    if n not in cache:
        computations += 1
        cache[n] = n * n
    return cache[n]


if __name__ == "__main__":
    assert square(3) == 9 and computations == 1
    assert square(3) == 9 and computations == 1
    assert square(4) == 16 and computations == 2
    # 改用立方规则时，平方规则下的缓存已经不适用。
    cache.clear()
    assert 3 not in cache
    cache[3] = 3 * 3 * 3
    assert cache[3] == 27
    print("PASS: 两次输入3只计算一次；输入4另算；更换规则后旧值被清除。")
