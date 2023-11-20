"""Parser module to parse gear config.json."""
from typing import Tuple
from zipfile import ZipFile
from flywheel_gear_toolkit import GearToolkitContext
import os
import logging
from fw_gear_fsl_topup.common import execute_shell, searchfiles
import errorhandler

log = logging.getLogger(__name__)

# Track if message gets logged with severity of error or greater
error_handler = errorhandler.ErrorHandler()

def parse_config(
        gear_context: GearToolkitContext,
) -> Tuple[dict, dict]:
    """Parse the config and other options from the context, both gear and app options.

    Returns:
        gear_options: options for the gear
        app_options: options to pass to the app
    """
    # ##   Gear config   ## #
    errors = []

    options = {"gear-log-level": gear_context.config.get("gear-log-level"),
               "output-dir": gear_context.output_dir,
               "destination-id": gear_context.destination["id"],
               "work-dir": gear_context.work_dir,
               "client": gear_context.client,
               "environ": os.environ,
               "output_analysis_id_dir": (
                gear_context.work_dir / gear_context.destination["id"]),
               "dry-run": gear_context.config.get("gear-dry-run")
        }

    options_keys = [
        "topup_only",
        "displacement_field",
        "jacobian_determinants",
        "rigid_body_matrix",
        "verbose",
        "topup_debug_level",
    ]
    options.update({key: gear_context.config.get(key) for key in options_keys})

    os.makedirs(options["output_analysis_id_dir"], exist_ok=True)

    # unzip input files
    if gear_context.get_input_path("preprocessing-pipeline-zip"):
        options["preproc_zip"] = True
        options["preproc_zipfile"] = gear_context.get_input_path("preprocessing-pipeline-zip")

        log.info("Preprocessed zip inputs file path, %s", options["preproc_zipfile"])
        rc, outpath = unzip_inputs(options, options["preproc_zipfile"])
        options["inputs-dir"] = os.path.join(outpath[0])

        # download fieldmaps from flywheel
        gear_context.download_session_bids(
            target_dir=os.path.join(gear_context.work_dir, outpath[0]),
            folders=['fmap']
        )

    # if no external input is passed - and BIDS mode used, download bids dir
    else:
        outpath = os.path.join(gear_context.work_dir, "BIDS")
        options["inputs-dir"] = os.path.join(outpath)

        gear_context.download_session_bids(
            target_dir=outpath
        )

    # check that bids derivative intended for json is also passed - if not, return error
    if gear_context.get_input_path("bids-derivative-intended-for"):
        options["intended_for"] = gear_context.get_input_path("bids-derivative-intended-for")

    if gear_context.get_input_path("_acquisition_parameters"):
        options["acq_par"] = gear_context.get_input_path('_acquisition_parameters')

    if gear_context.get_input_path("_config_file"):
       options["config_path"] = gear_context.get_input_path('_config_file')

    destination = gear_context.client.get(gear_context.destination["id"])
    sid = gear_context.client.get(destination.parents.subject)
    sesid = gear_context.client.get(destination.parents.session)

    options["sid"] = sid.label
    options["sesid"] = sesid.label



    options["fmaps"] = searchfiles(os.path.join(options["inputs-dir"],"sub-"+sid.label,"ses-"+sesid.label,"fmap/*.nii.gz"))

    return options


def unzip_inputs(gear_options, zip_filename):
    """
    unzip_inputs unzips the contents of zipped gear output into the working
    directory.
    Args:
        gear_options: The gear context object
            containing the 'gear_dict' dictionary attribute with key/value,
            'gear-dry-run': boolean to enact a dry run for debugging
        zip_filename (string): The file to be unzipped
    """
    rc = 0
    outpath=[]
    # use linux "unzip" methods in shell in case symbolic links exist
    log.info("Unzipping file, %s", zip_filename)
    cmd = "unzip -o " + zip_filename + " -d " + str(gear_options["work-dir"])
    execute_shell(cmd, cwd=gear_options["work-dir"])

    # if unzipped directory is a destination id - move all outputs one level up
    with ZipFile(zip_filename, "r") as f:
        top = [item.split('/')[0] for item in f.namelist()]
        top1 = [item.split('/')[1] for item in f.namelist()]
        try:
            top1.remove('')
        except:
            pass
    log.info("Done unzipping.")

    if len(top[0]) == 24:
        # directory starts with flywheel destination id - obscure this for now...
        cmd = "mv "+top[0]+'/* . ; rm -R '+top[0]
        execute_shell(cmd, cwd=gear_options["work-dir"])
        for i in set(top1):
            outpath.append(os.path.join(gear_options["work-dir"], i))

        # get previous gear info
        gear_options["preproc_gear"] = gear_options["client"].get(top[0])
    else:
        outpath = os.path.join(gear_options["work-dir"], top[0])

    if error_handler.fired:
        log.critical('Failure: exiting with code 1 due to logged errors')
        run_error = 1
        return run_error

    return rc, outpath


