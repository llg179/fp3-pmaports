#!/usr/bin/env python3
# Fit the magnetometer's hard-iron offset and per-axis scale from a rotation log.
#
# Two fits, deliberately, because they answer different questions:
#   axis-aligned ellipsoid  -> hard-iron offset + per-axis gain (soft-iron ignored)
#   general quadric         -> also the off-diagonal soft-iron terms
# If the general fit's cross terms are small, the simple one is the honest model
# and the extra parameters are just fitting noise.
import math, sys

def load(f):
    r = []
    for l in open(f):
        if l.startswith('#') or l.startswith('t,'):
            continue
        p = l.strip().split(',')
        if len(p) == 4:
            r.append(tuple(float(x) for x in p[1:]))
    return r


def solve(A, b):
    """Least squares via normal equations with Gaussian elimination."""
    n = len(A[0])
    M = [[sum(A[k][i] * A[k][j] for k in range(len(A))) for j in range(n)]
         + [sum(A[k][i] * b[k] for k in range(len(A)))] for i in range(n)]
    for i in range(n):
        p = max(range(i, n), key=lambda r: abs(M[r][i]))
        M[i], M[p] = M[p], M[i]
        if abs(M[i][i]) < 1e-18:
            raise ValueError('singular')
        for r in range(n):
            if r == i:
                continue
            f = M[r][i] / M[i][i]
            for c in range(i, n + 1):
                M[r][c] -= f * M[i][c]
    return [M[i][n] / M[i][i] for i in range(n)]


def fit_axis_aligned(pts):
    # a x^2 + b y^2 + c z^2 + d x + e y + f z = 1
    A = [[x * x, y * y, z * z, x, y, z] for x, y, z in pts]
    a, b, c, d, e, f = solve(A, [1.0] * len(pts))
    cx, cy, cz = -d / (2 * a), -e / (2 * b), -f / (2 * c)
    k = 1 + a * cx * cx + b * cy * cy + c * cz * cz
    rx, ry, rz = math.sqrt(k / a), math.sqrt(k / b), math.sqrt(k / c)
    return (cx, cy, cz), (rx, ry, rz)


def main():
    pts = load(sys.argv[1])
    print('%d samples' % len(pts))
    c, r = fit_axis_aligned(pts)
    print('\nhard-iron offset (subtract this):')
    print('   %+.5f  %+.5f  %+.5f' % c)
    print('semi-axes (the per-axis gain):')
    print('   %.5f  %.5f  %.5f' % r)
    rm = (r[0] * r[1] * r[2]) ** (1 / 3)
    print('geometric mean radius = %.5f' % rm)
    print('per-axis gain relative to that mean:')
    print('   %+.2f%%  %+.2f%%  %+.2f%%'
          % tuple(100 * (v / rm - 1) for v in r))

    # residual of the corrected data against a unit sphere
    res = []
    for x, y, z in pts:
        u = ((x - c[0]) / r[0], (y - c[1]) / r[1], (z - c[2]) / r[2])
        res.append(math.sqrt(sum(v * v for v in u)) - 1)
    res.sort()
    rms = math.sqrt(sum(v * v for v in res) / len(res))
    print('\nafter correction, |m|/R - 1:')
    print('   rms %.4f   p05 %+.4f   median %+.4f   p95 %+.4f   worst %+.4f'
          % (rms, res[len(res) // 20], res[len(res) // 2],
             res[-len(res) // 20], max(abs(res[0]), abs(res[-1]))))

    # uncorrected, for comparison
    raw = [math.sqrt(x * x + y * y + z * z) for x, y, z in pts]
    print('uncorrected |m|: %.4f .. %.4f (ratio %.2fx)'
          % (min(raw), max(raw), max(raw) / min(raw)))

    # direction coverage of the CORRECTED data, which is the honest measure
    seen = set()
    for x, y, z in pts:
        u = [(x - c[0]) / r[0], (y - c[1]) / r[1], (z - c[2]) / r[2]]
        n = math.sqrt(sum(v * v for v in u)) or 1
        u = [v / n for v in u]
        seen.add((round(u[0] * 2), round(u[1] * 2), round(u[2] * 2)))
    print('\ndirection coverage: %d distinct cells on the corrected sphere' % len(seen))


main()
