import numpy as np
from astropy.cosmology import Planck18
from astropy.units import Unit

from elisa import ConstantValue
from elisa.models import PhAbs, PLPhFlux, PowerLaw, ZAShift


def test_name():
    model1 = PowerLaw() + PowerLaw()
    model2 = PhAbs() * PowerLaw()
    model3 = ZAShift(1.0)(PowerLaw())

    assert model1.name == 'PowerLaw + PowerLaw_2'
    assert model2.name == 'PhAbs * PowerLaw'
    assert model3.name == 'ZAShift(PowerLaw)'


def test_lumin_and_eiso():
    def powerlaw(alpha, K, egrid):
        egrid = np.array(egrid)
        one_minus_alpha = 1.0 - alpha
        f = K / one_minus_alpha * np.power(egrid, one_minus_alpha)
        return f[1:] - f[:-1]

    flux_unit = Unit('keV cm^-2 s^-1')

    alpha = 2.5
    K = 1e4  # normalization at 1 keV, s^-1 cm^-2 keV^-1
    r = 1.0 * Unit('km')
    area = 4.0 * np.pi * r**2
    exposure = 1.0 * Unit('s')
    flux = powerlaw(alpha - 1.0, K, [1.0, 1e4]) * flux_unit
    eiso = flux * area * exposure
    eiso = eiso.to('erg').value
    lumin = eiso / exposure.value

    z = 3.0
    dc = Planck18.comoving_distance(z).to('km')
    factor = (r / dc) ** 2
    factor = factor.value
    K_obs = K * factor
    exposure_obs = exposure * (1 + z)

    # def zpowerlaw(alpha, K, egrid, z):
    #     egrid = np.array(egrid)
    #     return powerlaw(alpha, K, egrid * (1 + z)) / (1 + z)
    #
    # def zpowerlaw_flux_rest(alpha, K, egrid, z):
    #     alpha = alpha - 1.0
    #     egrid = np.array(egrid) / (1 + z)
    #     return zpowerlaw(alpha, K, egrid, z)
    #
    # area_1 = 4.0 * np.pi * dc**2
    # flux_obs = zpowerlaw_flux_rest(alpha, K_, [1, 10000], z) * flux_unit
    # eiso_obs = flux_obs * area_1 * exposure_obs
    # lumin_obs = eiso_obs / (exposure_obs / (1 + z))
    # eiso_obs = eiso_obs.to('erg').value
    # lumin_obs = lumin_obs.to('erg s^-1').value

    K_param = ConstantValue('K', K_obs)
    model = ZAShift(z)(PowerLaw(K=K_param, alpha=alpha)).compile()
    lumin_calc = model.lumin(1, 10000, z).value
    eiso_calc = model.eiso(1, 10000, z, exposure_obs.value).value

    assert np.allclose(lumin, lumin_calc)
    assert np.allclose(eiso, eiso_calc)


def test_simulation():
    def powerlaw(alpha, K, egrid):
        egrid = np.array(egrid)
        one_minus_alpha = 1.0 - alpha
        f = K / one_minus_alpha * np.power(egrid, one_minus_alpha)
        return f[1:] - f[:-1]

    seed = 42
    emin = 1.0
    emax = 100.0
    nbins = 10
    photon_egrid = np.linspace(emin, emax, nbins + 1)
    channel_emin = photon_egrid[:-1]
    channel_emax = photon_egrid[1:]
    response_matrix = np.eye(nbins)
    spec_exposure = 100.0
    back_exposure = 50.0
    background = np.ones(nbins) * 100.0

    rng = np.random.default_rng(seed)
    back_counts = rng.poisson(background)

    alpha = 2.5
    F = 1000.0  # photon flux between emin and emax
    unscaled_flux = powerlaw(alpha, 1.0, photon_egrid)
    factor = F / powerlaw(alpha, 1.0, [emin, emax])
    source = unscaled_flux * factor * spec_exposure
    total = source + spec_exposure * background / back_exposure
    total_counts = rng.poisson(total)

    model = PLPhFlux(emin, emax, F=F, alpha=alpha).compile()
    data = model.simulate(
        photon_egrid=photon_egrid,
        channel_emin=channel_emin,
        channel_emax=channel_emax,
        response_matrix=response_matrix,
        spec_exposure=spec_exposure,
        spec_poisson=True,
        back_counts=background,
        back_exposure=back_exposure,
        back_poisson=True,
        seed=seed,
    )

    assert np.all(data.spec_counts == total_counts)
    assert np.all(data.back_counts == back_counts)
