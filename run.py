#!/usr/bin/env python3

import os, sys
import logging
import shutil
from flywheel_gear_toolkit import GearToolkitContext
from pathlib import Path
from fw_gear_fsl_topup.main import prepare, run
from fw_gear_fsl_topup.parser import parse_config
from utils.singularity import run_in_tmp_dir

os.chdir("/flywheel/v0")

log = logging.getLogger(__name__)


def main(context: GearToolkitContext):
    """Main TOPUP correction script

    This script runs TOPUP on a BIDS derivative dataset. If no additional pre-processed data are passed, run on the bids
    raw dataset, otherwise, respect the prerpcessed input and provided intended for to assign distortion correction.

    Returns: return_code

    """

    FWV0 = Path.cwd()
    log.info("Running gear in %s", FWV0)
    output_dir = context.output_dir
    log.info("output_dir is %s", output_dir)
    work_dir = context.work_dir
    log.info("work_dir is %s", work_dir)

    # initiate return_code
    return_code = 0

    """Parses config and runs."""
    # For now, don't allow runs at the project level:
    destination = context.client.get(context.destination["id"])
    if destination.parent.type == "project":
        log.exception(
            "This version of the gear does not run at the project level. "
            "Try running it for each individual subject."
        )
        # sys.exit(1)
        return_code = 1

    # Errors and warnings will always be logged when they are detected.
    # Keep a list of errors and warning to print all in one place at end of log
    # Any errors will prevent the BIDS App from running.
    errors = []
    warnings = []

    # Call the fw_gear_bids_qsiprep.parser.parse_config function
    # to extract the args, kwargs from the context (e.g. config.json).
    options = parse_config(context)

    # #adding the usual environment call
    # environ = get_and_log_environment()

    prepare_errors, prepare_warnings = prepare(
        options=options,
    )
    errors += prepare_errors
    warnings += prepare_warnings

    if len(errors) > 0:
        e_code = 1
        log.info("Command was NOT run because of previous errors.")

    else:
        try:
            # Pass the args, kwargs to fw_gear_qsiprep.main.run function to execute
            # the main functionality of the gear.
            e_code = run(options, context)


        except RuntimeError as exc:
            e_code = 1
            errors.append(str(exc))
            log.critical(exc)
            log.exception("Unable to execute command.")

        else:
            # We want to save the metadata only if the run was successful.
            # We want to save partial outputs in the event of the app crashing, because
            # the partial outputs can help pinpoint what the exact problem was. So we
            # have `post_run` further down.

            # save_metadata(context, gear_options["output_analysis_id_dir"] / "qsiprep")
            pass

    return e_code


# Only execute if file is run as main, not when imported by another module
if __name__ == "__main__":  # pragma: no cover
    # Get access to gear config, inputs, and sdk client if enabled.
    with GearToolkitContext() as gear_context:
        # Initialize logging, set logging level based on `debug` configuration
        # key in gear config.
        gear_context.init_logging()
        log.parent.handlers[0].setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
        log.setLevel(gear_context.config['gear-log-level'])

        scratch_dir = run_in_tmp_dir(gear_context.config["gear-writable-dir"])

    # Has to be instantiated twice here, since parent directories might have
    # changed
    with GearToolkitContext() as gear_context:

        # Pass the gear context into main function defined above.
        return_code = main(gear_context)

    # clean up (might be necessary when running in a shared computing environment)
    if scratch_dir:
        log.debug("Removing scratch directory")
        for thing in scratch_dir.glob("*"):
            if thing.is_symlink():
                thing.unlink()  # don't remove anything links point to
                log.debug("unlinked %s", thing.name)
        shutil.rmtree(scratch_dir)
        log.debug("Removed %s", scratch_dir)

    sys.exit(return_code)
