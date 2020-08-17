# Copyright 2020 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os

import argparse
import matplotlib.pyplot as plt
import numpy as np
import torch
import tqdm
from scipy import stats

from tests.problems import Ex2
from torchsde import sdeint, BrownianInterval
from torchsde.settings import LEVY_AREA_APPROXIMATIONS
from .utils import to_numpy, makedirs_if_not_found, compute_mse


def inspect_sample():
    batch_size, d = 32, 1
    steps = 100

    ts = torch.linspace(0., 5., steps=steps, device=device)
    dt = 1e-1
    y0 = torch.ones(batch_size, d, device=device)
    sde = Ex2(d=d).to(device)
    sde_strat = Ex2(d=d, sde_type='stratonovich').to(device)
    sde_strat.p = sde.p

    with torch.no_grad():
        bm = BrownianInterval(t0=ts[0], t1=ts[-1], shape=y0.shape, dtype=y0.dtype, device=device,
                              levy_area_approximation=LEVY_AREA_APPROXIMATIONS.space_time)

        ys_euler = sdeint(sde, y0=y0, ts=ts, dt=dt, bm=bm, method='euler')
        ys_heun = sdeint(sde_strat, y0=y0, ts=ts, dt=dt, bm=bm, method='heun', names={'drift': 'f_corr'})
        ys_midpoint = sdeint(sde_strat, y0=y0, ts=ts, dt=dt, bm=bm, method='midpoint', names={'drift': 'f_corr'})
        ys_analytical = sde.analytical_sample(y0=y0, ts=ts, bm=bm)

        ys_euler = ys_euler.squeeze().t()
        ys_heun = ys_heun.squeeze().t()
        ys_midpoint = ys_midpoint.squeeze().t()
        ys_analytical = ys_analytical.squeeze().t()

        ts_, ys_euler_, ys_heun_, ys_midpoint_, ys_analytical_ = to_numpy(
            ts, ys_euler, ys_heun, ys_midpoint, ys_analytical)

    # Visualize sample path.
    img_dir = os.path.join('.', 'diagnostics', 'plots', 'stratonovich_diagonal')
    makedirs_if_not_found(img_dir)

    for i, (ys_euler_i, ys_heun_i, ys_midpoint_i, ys_analytical_i) in enumerate(
            zip(ys_euler_, ys_heun_, ys_midpoint_, ys_analytical_)):
        plt.figure()
        plt.plot(ts_, ys_euler_i, label='euler')
        plt.plot(ts_, ys_heun_i, label='heun')
        plt.plot(ts_, ys_midpoint_i, label='midpoint')
        plt.plot(ts_, ys_analytical_i, label='analytical')
        plt.legend()
        plt.savefig(os.path.join(img_dir, f'{i}'))
        plt.close()


def inspect_strong_order():
    batch_size, d = 4096, 10
    ts = torch.tensor([0., 5.], device=device)
    dts = tuple(2 ** -i for i in range(1, 9))
    y0 = torch.ones(batch_size, d, device=device)
    sde = Ex2(d=d).to(device)
    sde_strat = Ex2(d=d, sde_type='stratonovich').to(device)
    sde_strat.p = sde.p

    euler_mses_ = []
    heun_mses_ = []
    midpoint_mses_ = []

    with torch.no_grad():
        bm = BrownianInterval(t0=ts[0], t1=ts[-1], shape=y0.shape, dtype=y0.dtype, device=device,
                              levy_area_approximation=LEVY_AREA_APPROXIMATIONS.space_time)

        for dt in tqdm.tqdm(dts):
            # Only take end value.
            _, ys_euler = sdeint(sde, y0=y0, ts=ts, dt=dt, bm=bm, method='euler')
            _, ys_heun = sdeint(sde_strat, y0=y0, ts=ts, dt=dt, bm=bm, method='heun', names={'drift': 'f_corr'})
            _, ys_midpoint = sdeint(sde_strat, y0=y0, ts=ts, dt=dt, bm=bm, method='midpoint', names={'drift': 'f_corr'})
            _, ys_analytical = sde.analytical_sample(y0=y0, ts=ts, bm=bm)

            euler_mse = compute_mse(ys_euler, ys_analytical)
            heun_mse = compute_mse(ys_heun, ys_analytical)
            midpoint_mse = compute_mse(ys_midpoint, ys_analytical)

            euler_mse_, heun_mse_, midpoint_mse_ = to_numpy(euler_mse, heun_mse, midpoint_mse)

            euler_mses_.append(euler_mse_)
            heun_mses_.append(heun_mse_)
            midpoint_mses_.append(midpoint_mse_)
    del euler_mse_, heun_mse_, midpoint_mse_

    # Divide the log-error by 2, since textbook strong orders are represented so.
    log = lambda x: np.log(np.array(x))
    euler_slope, _, _, _, _ = stats.linregress(log(dts), log(euler_mses_) / 2)
    heun_slope, _, _, _, _ = stats.linregress(log(dts), log(heun_mses_) / 2)
    midpoint_slope, _, _, _, _ = stats.linregress(log(dts), log(midpoint_mses_) / 2)

    plt.figure()
    plt.plot(dts, euler_mses_, label=f'euler(k={euler_slope:.4f})')
    plt.plot(dts, heun_mses_, label=f'heun(k={heun_slope:.4f})')
    plt.plot(dts, midpoint_mses_, label=f'midpoint(k={midpoint_slope:.4f})')
    plt.xscale('log')
    plt.yscale('log')
    plt.legend()

    img_dir = os.path.join('.', 'diagnostics', 'plots', 'stratonovich_diagonal')
    makedirs_if_not_found(img_dir)
    plt.savefig(os.path.join(img_dir, 'rate'))
    plt.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--no-gpu', action='store_true')

    args = parser.parse_args()
    device = torch.device('cuda' if torch.cuda.is_available() and not args.no_gpu else 'cpu')
    torch.set_default_dtype(torch.float64)
    torch.manual_seed(0)

    inspect_sample()
    inspect_strong_order()