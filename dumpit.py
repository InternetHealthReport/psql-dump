import argparse
import json
import logging
import os

import arrow


class Dumper():
    def __init__(self, config_fname):
        """ Initialize crawler with variables from config file"""

        with open(config_fname, 'r') as fp:
            self.config = json.load(fp)

    def fname(self, startdate):
        """Construct the folder and filename for the given date and config file"""

        dump_folder = os.path.join(self.config['dump_root'], startdate.format('YYYY/MM/DD'))
        dump_fname = f'{self.config["dump_fname"]}_{startdate.format("YYYY-MM-DD")}.csv'

        return dump_folder, dump_fname

    def dump(self, date, compress='lz4'):

        startdate = date
        enddate = date.shift(days=1)

        query = self.config['query'].format(startdate=startdate, enddate=enddate)
        dump_folder, dump_fname = self.fname(startdate)
        intermediate_output_file = os.path.join(dump_folder, dump_fname)
        final_output_file = intermediate_output_file
        if compress:
            final_output_file += f'.{compress}'

        # Check if dump already exists
        if os.path.exists(final_output_file):
            logging.error(f'{final_output_file} already exists')
            return

        # create directories if needed
        os.makedirs(dump_folder, exist_ok=True)

        cmd = r"""psql -d {db} -h {psql_host} -U {psql_role} -c "\copy ({query}) to '{fname}' csv header;" """.format(
            db=self.config['database'],
            psql_host=PSQL_HOST,
            psql_role=PSQL_ROLE,
            query=query,
            fname=intermediate_output_file
        )

        logging.debug(f'Dumping data to csv file ({cmd})...')
        ret_value = os.system(cmd)
        if ret_value != 0:
            logging.error(f'Could not dump data? Returned value: {ret_value}')

        if compress:
            cmd = f'{compress} -f {intermediate_output_file} {final_output_file}'
            logging.debug(f'Compressing data ({cmd})...')
            ret_value = os.system(cmd)
            os.remove(intermediate_output_file)

        if ret_value != 0:
            logging.error(f'Could not compress data? Returned value: {ret_value}')

        if not os.path.exists(final_output_file):
            logging.error(f'No output file created: {final_output_file}')
            return

        if os.path.getsize(final_output_file) < 1000:
            logging.warning(f'Output file was empty. Deleting {final_output_file}')
            os.remove(final_output_file)


if __name__ == "__main__":
    logging.basicConfig(
        format='%(asctime)s %(processName)s %(message)s',
        level=logging.INFO,
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[logging.StreamHandler()])

    global PSQL_HOST
    PSQL_HOST = os.environ["PSQL_HOST"]
    global PSQL_ROLE
    PSQL_ROLE = os.environ["PSQL_ROLE"]

    parser = argparse.ArgumentParser(
        description='Dump data from the database to a CSV file')
    parser.add_argument('--config', type=str,
                        help='configuration file with query and file structure details')
    parser.add_argument('--dates', default='', type=str,
                        help='file containing a list of dates to dump (one date per line)')
    parser.add_argument('--date', default='', type=str,
                        help='date to dump (e.g. 2022-01-20)')
    parser.add_argument('--startdate', default='', type=str,
                        help='start date for a range of dates. Should also specify enddate')
    parser.add_argument('--enddate', default='', type=str,
                        help='end date for a range of dates. Should also specify startdate')
    parser.add_argument('--frequency', default='day', type=str,
                        help='frequency for a range of dates (default: day)')

    args = parser.parse_args()

    # Retrieve dates from file or set it to yesterday
    dates = []
    if args.dates:
        with open(args.dates, 'r') as fp:
            for date in fp.readlines():
                dates.append(arrow.get(date.strip()))
    elif args.startdate and args.enddate and args.frequency:
        start = arrow.get(args.startdate)
        end = arrow.get(args.enddate)
        for date in arrow.Arrow.range(args.frequency, start, end):
            dates.append(date)
    elif args.date:
        dates.append(arrow.get(args.date))
    else:
        dates.append(arrow.utcnow().shift(days=-1))

    try:
        for date in dates:
            dumper = Dumper(config_fname=args.config)
            dumper.dump(date)

    # Log any error that could happen
    except Exception as e:
        logging.error('Error', exc_info=e)
