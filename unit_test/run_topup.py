
import os
import os.path as op
from fw_gear_fsl_topup.common import searchfiles
from fw_gear_fsl_topup.parser import parse_config
from flywheel_gear_toolkit import GearToolkitContext
import logging
os.chdir("/flywheel/v0")

from fw_gear_fsl_topup.main import generate_topup_input, generate_acquisition_params, run_topup, \
    locate_fieldmap_pairs, locate_apply_to_files, apply_topup

log = logging.getLogger(__name__)

os.chdir("/flywheel/v0")
with GearToolkitContext() as gear_context:
    log.setLevel(gear_context.config['gear-log-level'])
    gear_context.log_config()

    options = parse_config(gear_context)


pairs = locate_fieldmap_pairs(options["fmaps"])

for imgs in pairs:

    log.info("Using fieldmaps: %s", ", ".join(imgs))

    # Run Topup on the inputs
    log.info('Running Topup')

    topup_dir = os.path.join(options["work-dir"],"topup")
    os.makedirs(topup_dir, exist_ok=True)

    options["Image1"] = imgs[0]
    options["Image2"] = imgs[1]

    topup_dir = os.path.join(options["work-dir"],"topup")
    os.makedirs(topup_dir, exist_ok=True)

    topup_input = generate_topup_input(options)

    acq_input = generate_acquisition_params(options)

    # topup_out = run_topup(options, topup_input, acq_input, topup_dir)
    topup_out = '/flywheel/v0/work/topup/topup'

    log.info('Checking intended-fors')

    apply_to_files, acq_param_idxs = locate_apply_to_files(options)

    # Try to apply topup to input files
    log.info('Applying Topup Correction')
    corrected_files = apply_topup(apply_to_files, acq_param_idxs, topup_out, acq_input)