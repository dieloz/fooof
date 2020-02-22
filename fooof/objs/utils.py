"""Utility functions for managing and manipulating FOOOF objects."""

import numpy as np

from fooof.data import FOOOFResults
from fooof.objs import FOOOF, FOOOFGroup
from fooof.analysis.periodic import get_band_peak_fg
from fooof.core.errors import NoModelError, IncompatibleSettingsError

###################################################################################################
###################################################################################################

def compare_info(fooof_lst, aspect):
    """Compare a specified aspect of FOOOF objects across instances.

    Parameters
    ----------
    fooof_lst : list of FOOOF and / or FOOOFGroup
        Objects whose attributes are to be compared.
    aspect : {'settings', 'meta_data'}
        Which set of attributes to compare the objects across.

    Returns
    -------
    consistent : bool
        Whether the settings are consistent across the input list of objects.
    """

    # Check specified aspect of the objects are the same across instances
    for f_obj_1, f_obj_2 in zip(fooof_lst[:-1], fooof_lst[1:]):
        if getattr(f_obj_1, 'get_' + aspect)() != getattr(f_obj_2, 'get_' + aspect)():
            consistent = False
            break
    else:
        consistent = True

    return consistent


def average_fg(fg, bands, avg_method='mean', regenerate=True):
    """Average across model fits in a FOOOFGroup object.

    Parameters
    ----------
    fg : FOOOFGroup
        Object with model fit results to average across.
    bands : Bands
        Bands object that defines the frequency bands to collapse peaks across.
    avg : {'mean', 'median'}
        Averaging function to use.
    regenerate : bool, optional, default: True
        Whether to regenerate the model for the averaged parameters.

    Returns
    -------
    fm : FOOOF
        Object containing the average model results.

    Raises
    ------
    ValueError
        If the requested averaging method is not understood.
    NoModelError
        If there are no model fit results available to average across.
    """

    if avg_method not in ['mean', 'median']:
        raise ValueError("Requested average method not understood.")
    if not fg.has_model:
        raise NoModelError("No model fit results are available, can not proceed.")

    if avg_method == 'mean':
        avg_func = np.nanmean
    elif avg_method == 'median':
        avg_func = np.nanmedian

    # Aperiodic parameters: extract & average
    ap_params = avg_func(fg.get_params('aperiodic_params'), 0)

    # Periodic parameters: extract & average
    peak_params = []
    gauss_params = []

    for band_def in bands.definitions:

        peaks = get_band_peak_fg(fg, band_def, attribute='peak_params')
        gauss = get_band_peak_fg(fg, band_def, attribute='gaussian_params')

        # Check if there are any extracted peaks - if not, don't add
        #   Note that we only check peaks, but gauss should be the same
        if not np.all(np.isnan(peaks)):
            peak_params.append(avg_func(peaks, 0))
            gauss_params.append(avg_func(gauss, 0))

    peak_params = np.array(peak_params)
    gauss_params = np.array(gauss_params)

    # Goodness of fit measures: extract & average
    r2 = avg_func(fg.get_params('r_squared'))
    error = avg_func(fg.get_params('error'))

    # Collect all results together, to be added to FOOOF object
    results = FOOOFResults(ap_params, peak_params, r2, error, gauss_params)

    # Create the new FOOOF object, with settings, data info & results
    fm = FOOOF()
    fm.add_settings(fg.get_settings())
    fm.add_meta_data(fg.get_meta_data())
    fm.add_results(results)

    # Generate the average model from the parameters
    if regenerate:
        fm._regenerate_model()

    return fm


def combine_fooofs(fooofs):
    """Combine a group of FOOOF and/or FOOOFGroup objects into a single FOOOFGroup object.

    Parameters
    ----------
    fooofs : list of FOOOF or FOOOFGroup
        Objects to be concatenated into a FOOOFGroup.

    Returns
    -------
    fg : FOOOFGroup
        Resultant object from combining inputs.

    Raises
    ------
    IncompatibleSettingsError
        If the input objects have incompatible settings for combining.
    """

    # Compare settings
    if not compare_info(fooofs, 'settings') or not compare_info(fooofs, 'meta_data'):
        raise IncompatibleSettingsError("These objects have incompatible settings "
                                        "or meta data, and so cannot be combined.")

    # Initialize FOOOFGroup object, with settings derived from input objects
    fg = FOOOFGroup(*fooofs[0].get_settings(), verbose=fooofs[0].verbose)

    # Use a temporary store to collect spectra, because we only add them if consistently present
    temp_power_spectra = np.empty([0, len(fooofs[0].freqs)])

    # Add FOOOF results from each FOOOF object to group
    for f_obj in fooofs:

        # Add FOOOFGroup object
        if isinstance(f_obj, FOOOFGroup):
            fg.group_results.extend(f_obj.group_results)
            if f_obj.power_spectra is not None:
                temp_power_spectra = np.vstack([temp_power_spectra, f_obj.power_spectra])

        # Add FOOOF object
        else:
            fg.group_results.append(f_obj.get_results())
            if f_obj.power_spectrum is not None:
                temp_power_spectra = np.vstack([temp_power_spectra, f_obj.power_spectrum])

    # If the number of collected power spectra is consistent, then add them to object
    if len(fg) == temp_power_spectra.shape[0]:
        fg.power_spectra = temp_power_spectra

    # Add data information information
    fg.add_meta_data(fooofs[0].get_meta_data())

    return fg


def fit_fooof_group_3d(fg, freqs, power_spectra, freq_range=None, n_jobs=1):
    """Run FOOOFGroup across a 3D collection of power spectra.

    Parameters
    ----------
    fg : FOOOFGroup
        Object to fit with, initialized with desired settings.
    freqs : 1d array
        Frequency values for the power spectra, in linear space.
    power_spectra : 3d array
        Power values, in linear space, with shape as: [n_conditions, n_power_spectra, n_freqs].
    freq_range : list of [float, float], optional
        Desired frequency range to fit. If not provided, fits the entire given range.
    n_jobs : int, optional, default: 1
        Number of jobs to run in parallel.
        1 is no parallelization. -1 uses all available cores.

    Returns
    -------
    fgs : list of FOOOFGroups
        Collected FOOOFGroups after fitting across power spectra, length of n_conditions.
    """

    fgs = []
    for cond_spectra in power_spectra:
        fg.fit(freqs, cond_spectra, freq_range, n_jobs)
        fgs.append(fg.copy())

    return fgs
