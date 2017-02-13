import schedule
import eventlet

from oslo_service import service
from oslo_config import cfg
from oslo_log import log as logging
LOG = logging.getLogger(__name__)

from murano.db import session as db_session
from murano.db import models
from murano.services import states

from murano.db.services import sessions

def get_scheduler_id():
    return '40b590492fca4ccfbb39a55c2d9b3269'

from murano.services import actions
import datetime
class SchedulerService(service.Service):
    def __init__(self):
        super(SchedulerService, self).__init__()
        self.unit = db_session.get_session()
        self.services = []

    def start(self):
        super(SchedulerService, self).start()
        self.tg.add_thread(self._collect_schedule_loop)

    def stop(self):
        super(SchedulerService, self).stop()

    @staticmethod
    def do(unit, session, d_mode):
        schedule.clear(session.id)
        if d_mode == 'MINUTE':
            schedule.every().minute.do(SchedulerService.do, unit, session, d_mode).tag(session.id)
        elif d_mode == 'HOUR':
            schedule.every().hour.do(SchedulerService.do, unit, session, d_mode).tag(session.id)
        elif d_mode == 'DAY':
            schedule.every().day.do(SchedulerService.do, unit, session, d_mode).tag(session.id)
        elif d_mode == 'WEEK':
            schedule.every().week.do(SchedulerService.do, unit, session, d_mode).tag(session.id)
        elif d_mode == 'MONTH':
            schedule.every(30).days.do(SchedulerService.do, unit, session, d_mode).tag(session.id)
        elif d_mode == 'YEAR':
            schedule.every(365).days.do(SchedulerService.do, unit, session, d_mode).tag(session.id)
        LOG.info('session {0} rescheduled...'.format(session.id))

        try:
            environment = unit.query(models.Environment).get(get_scheduler_id())
            if (session.description['Objects'] is not None or 'ObjectsCopy' not in session.description):
                sessions.SessionServices.deploy(session, environment, unit, session.description['SystemData']['Token'])
                #actions.ActionServices.submit_task('do', service, {}, environment, session, session.description['SystemData']['Token'], unit)
        except Exception:
            LOG.info('error in running schedule session {0}...'.format(session.id), exc_info=True)

    @staticmethod
    def tick(d_date, d_time):
        l = len(d_time.split(":"))
        if l == 3:
            s_datetime = '{0} {1}.0'.format(d_date, d_time)
        elif l == 2:
            s_datetime = '{0} {1}:0.0'.format(d_date, d_time)
        elif l == 1:
            s_datetime = '{0} {1}:0:0.0'.format(d_date, d_time)
        d_datetime = datetime.datetime.strptime(s_datetime, '%Y-%m-%d %H:%M:%S.%f')
        return (d_datetime-datetime.datetime.now()).total_seconds()

    @staticmethod
    def fix_tick(d_tick, period):
        return d_tick-int((d_tick+0.1)/period-1)*period

    def execute(self):
        services = []
        schedules = self.unit.query(models.Session).filter_by(environment_id=get_scheduler_id())
        for session in schedules:
            if session.description['Objects'].has_key('services'):
                if session.id not in self.services:
                    LOG.info('scheduling session {0}...'.format(session.id))
                    for service in session.description['Objects']['services']:
                        d_date = service.get('date', '1900-1-1')
                        d_time = service.get('time', '0:0:0')
                        d_mode = service.get('mode', 'ONCE')
                        d_tick = SchedulerService.tick(d_date, d_time)
                        if d_tick < 0 and session.state != states.EnvironmentStatus.PENDING:
                            if d_mode == 'ONCE':
                                continue
                            elif d_mode == 'MINUTE':
                                d_tick = SchedulerService.fix_tick(d_tick, 60)
                            elif d_mode == 'HOUR':
                                d_tick = SchedulerService.fix_tick(d_tick, 3600)
                            elif d_mode == 'DAY':
                                d_tick = SchedulerService.fix_tick(d_tick, 86400)
                            elif d_mode == 'WEEK':
                                d_tick = SchedulerService.fix_tick(d_tick, 604800)
                            elif d_mode == 'MONTH':
                                d_tick = SchedulerService.fix_tick(d_tick, 2592000)
                            elif d_mode == 'YEAR':
                                d_tick = SchedulerService.fix_tick(d_tick, 31536000)
                        schedule.every(d_tick).seconds.do(SchedulerService.do, self.unit, session, d_mode).tag(session.id)
                        LOG.info('session {0}:{1} scheduled...'.format(session.id, service['?']['id']))
                services.append(session.id)
            #for service in session.description['Objects'].get('services', []):
            #    if service['?']['id'] not in self.services:
            #        schedule.every(5).seconds.do(SchedulerService.do, self.unit, session, True).tag(service['?']['id'])
            #    services.append(service['?']['id'])
        for service in self.services:
            if service not in services:
                LOG.info('schedule session {0} cleared...'.format(service))
                schedule.clear(service)
        self.services = services

    def _collect_schedule_loop(self):
        LOG.info('scheduler start...')
        while True:
            try:
                self.execute()
                schedule.run_pending()
            except Exception:
                LOG.warning('scheduler execute error...', exc_info=True)
            eventlet.sleep(cfg.CONF.murano.period)
