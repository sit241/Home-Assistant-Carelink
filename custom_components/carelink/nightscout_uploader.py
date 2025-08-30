import argparse
import asyncio
from datetime import datetime
import hashlib
import json
import logging

import httpx

from .const import (
    CARELINK_CODE_MAP,
)

NS_USER_AGENT= "Home Assistant Carelink"
DEBUG = False

_LOGGER = logging.getLogger(__name__)


def printdbg(msg):
    """Debug logger/print function"""
    _LOGGER.debug("Nightscout API: %s", msg)

    if DEBUG:
        print(msg)

class NightscoutUploader:
    """Nightscout Uploader library"""

    def __init__(
        self,
        nightscout_url,
        nightscout_secret
    ):

        # Nightscout info
        self.__nightscout_url = nightscout_url.lower().rstrip('/')
        self.__hashedSecret = hashlib.sha1(nightscout_secret.encode('utf-8')).hexdigest()
        self.__is_reachable=False

        self._async_client = None
        self.__common_headers = {
            # Common browser headers
            'API-SECRET' : self.__hashedSecret,
            'Content-Type': "application/json",
            'User-Agent': NS_USER_AGENT,
            'Accept': 'application/json',
        }

    @property
    def async_client(self):
        """Return the httpx client."""
        if not self._async_client:
            self._async_client = httpx.AsyncClient()

        return self._async_client

    async def fetch_async(self, url, headers, params=None):
        """Perform an async get request."""
        response = await self.async_client.get(
            url,
            headers=headers,
            params=params,
            follow_redirects=True,
            timeout=30,
        )
        return response

    async def post_async(self, url, headers, data=None, params=None):
        """Perform an async post request."""
        response = await self.async_client.post(
            url,
            headers=headers,
            params=params,
            data=data,
            follow_redirects=True,
            timeout=30,
        )
        return response

    def __get_carbs(self, input_insulin, input_meal):
        result = dict()
        for marker in input_insulin:
            for entry in marker.items():
                for meal in input_meal:
                    if entry[0] in meal:
                        result[entry[0]]={"insulin" : entry[1] , "carb" : meal[entry[0]]}
        return result

    def __get_dict_values(self, input, key, value):
        result = list()
        for marker in input:
            markerDict=dict()
            if key in marker and marker["data"] and marker["data"]["dataValues"] and value in marker["data"]["dataValues"]:
                markerDict[marker[key]]=marker["data"]["dataValues"][value]
                result.append(markerDict)
        return result

    def __traverse(self, value, key=None):
        if isinstance(value, dict):
            for k, v in value.items():
                yield from self.__traverse(v, k)
        else:
            yield key, value

    def __get_treatments(self, input, key, value):
        result = list()
        for marker in input:
            markerDict=dict()
            isType=False
            for k, v in self.__traverse(marker):
                if key == k and v == value:
                    isType=True
                    break
            if isType:
                for entry in marker.items():
                    markerDict[entry[0]]=entry[1]
                result.append(markerDict)
        return result

    def __getDataStringFromIso(self, time, tz):
        dt = datetime.fromisoformat(time.replace(".000-00:00", ""))
        dt = dt.replace(tzinfo=tz)
        dt = dt.astimezone(tz)
        timestamp = dt.timestamp()
        date = int(timestamp * 1000)
        date_string = dt.isoformat()
        return date, date_string

    async def __setDeviceStatus(self, rawdata):
        printdbg("__setDeviceStatus()")
        try:
            data = self.__getDeviceStatus(rawdata)
        except Exception as error:
            printdbg(f"__setDeviceStatus() exeption: {error}")
            data = []
        return await self.__set_data(
            self.__nightscout_url, data, "devicestatus"
        )

    async def __setSGS(self, rawdata, tz):
        printdbg("__setSGS()")
        try:
            data = self.__getSGS(rawdata, tz)
        except Exception as error:
            printdbg(f"__setSGS() exeption: {error}")
            data = []
        return await self.__set_data(
            self.__nightscout_url, data, "entries"
        )

    async def __setBasal(self, rawdata, tz):
        printdbg("__setBasal()")
        try:
            data = self.__getBasal(rawdata, tz)
        except Exception as error:
            printdbg(f"__setBasal() exeption: {error}")
            data = []
        return await self.__set_data(
            self.__nightscout_url, data, "treatments"
        )

    async def __setBolus(self, rawdata, tz):
        printdbg("------------- Trying to get a bolus --------------")
        try:
            data = self.__getBolus(rawdata, tz)
            printdbg(data)
        except Exception as error:
            printdbg(f"__setBolus() exeption: {error}")
            data = []
        return await self.__set_data(
            self.__nightscout_url, data, "treatments"
        )

    async def __setAutoBolus(self, rawdata, tz):
        printdbg("__setAutoBolus()")
        try:
            data = self.__getAutoBolus(rawdata, tz)
        except Exception as error:
            printdbg(f"__setAutoBolus() exeption: {error}")
            data = []
        return await self.__set_data(
            self.__nightscout_url, data, "treatments"
        )

    async def __setAlarms(self, rawdata, tz):
        printdbg("__setAlarms()")
        try:
            data = self.__getAlarms(rawdata, tz)
        except Exception as error:
            printdbg(f"__setAlarms() exeption: {error}")
            data = []
        return await self.__set_data(
            self.__nightscout_url, data, "treatments"
        )

    async def __setMsgs(self, rawdata, tz):
        printdbg("__setMsgs()")
        try:
            data = self.__getMsgs(rawdata, tz)
        except Exception as error:
            printdbg(f"__setMsgs() exeption: {error}")
            data = []
        return await self.__set_data(
            self.__nightscout_url, data, "treatments"
        )

    async def __setAlerts(self, rawdata, tz):
        printdbg("__setAlerts()")
        try:
            data = self.__getAlerts(rawdata, tz)
        except Exception as error:
            printdbg(f"__setAlerts() exeption: {error}")
            data = []
        return await self.__set_data(
            self.__nightscout_url, data, "treatments"
        )

    async def __set_data(self, host, data, data_type):
        printdbg("__set_data()")
        if len(data) == 0:
            _LOGGER.info("Nightscout: нет данных для отправки в %s", data_type)
            return False
    
        url = f"{host}/api/v1/{data_type}"
        success = True
        try:
            for entry in data:
                _LOGGER.info("Nightscout: отправка %s -> %s", data_type, url)
                response = await self.post_async(url, headers=self.__common_headers, data=json.dumps(entry))
                if response.status_code == 200:
                    _LOGGER.info("Nightscout: успешно отправлено в %s", data_type)
                else:
                    _LOGGER.error("Nightscout: ошибка %s при отправке в %s", response.status_code, data_type)
                    success = False
        except Exception as error:
            _LOGGER.error("Nightscout: исключение при отправке в %s: %s", data_type, error)
            success = False
        return success

    def __getMsgs(self, rawdata, tz):
        msgs=self.__get_treatments(rawdata["clearedNotifications"], "type", "MESSAGE")
        return self.__getMsgEntries(msgs, tz)

    def __getAlarms(self, rawdata, tz):
        alarms=self.__get_treatments(rawdata["clearedNotifications"], "type", "ALARM")
        return self.__getMsgEntries(alarms, tz)

    def __getAlerts(self, rawdata, tz):
        alerts=self.__get_treatments(rawdata["clearedNotifications"], "type", "ALERT")
        return self.__getMsgEntries(alerts, tz)

    def __getMsgEntries(self, raw, tz):
        result = list()
        for msg in raw:
            date, date_string=self.__getDataStringFromIso(msg["dateTime"], tz)
            if "additionalInfo" in msg and "sg" in msg["additionalInfo"] and int(msg["additionalInfo"]["sg"]) < 400:
                result.append(dict(
                    timestamp=date,
                    enteredBy=NS_USER_AGENT,
                    created_at=date_string,
                    eventType="Note",
                    glucoseType="sensor",
                    glucose=float(msg["additionalInfo"]["sg"]),
                    notes=self.__getNote(CARELINK_CODE_MAP.setdefault(int(msg['faultId']), "Unknown"))
                    ))
            else:
                result.append(dict(
                    timestamp=date,
                    enteredBy=NS_USER_AGENT,
                    created_at=date_string,
                    eventType="Note",
                    notes=self.__getNote(CARELINK_CODE_MAP.setdefault(int(msg['faultId']), "Unknown"))
                    ))
        return result

    def __getNote(self, msg):
        return msg.replace("BC_SID_", "").replace("BC_MESSAGE_", "")

    def __getBolus(self, raw, tz):
        # Local Helper: It is safe to show the data slice for the log
        def _preview(name, obj, n=2):
            try:
                if obj is None:
                    printdbg(f"{name}: None"); return
                if isinstance(obj, list):
                    printdbg(f"{name}: type=list, len={len(obj)}, head={obj[:n]}")
                elif isinstance(obj, dict):
                    it = list(obj.items())[:n]
                    printdbg(f"{name}: type=dict, len={len(obj)}, head={it}")
                else:
                    printdbg(f"{name}: type={type(obj).__name__}, value={obj}")
            except Exception as e:
                printdbg(f"{name}: <preview error: {e!r}>")

        # Извлечь значение из возможных мест/имён
        def _get_any(dct, *keys, default=None):
            for k in keys:
                if isinstance(dct, dict) and k in dct and dct[k] is not None:
                    return dct[k]
            return default

        # Глубокий поиск по возможным путям: ("data","dataValues","deliveredFastAmount") и т.п.
        def _deep_get(obj, path, default=None):
            cur = obj
            for k in path:
                if not isinstance(cur, dict) or k not in cur:
                    return default
                cur = cur[k]
            return cur

        # Простой ISO->datetime (timezone-aware)
        from datetime import datetime, timezone, timedelta
        def _parse_iso(ts):
            try:
                # На входе "2025-08-29T22:15:55" (без tz) — считаем, что это локально, потом нормализуем в tz ниже
                dt = datetime.fromisoformat(str(ts))
                return dt.replace(tzinfo=tz)
            except Exception:
                return None

        # Сопоставить по времени: точное совпадение или ближайшее в пределах window
        def _merge_by_time(ins_by_ts, carbs_by_ts, window=timedelta(minutes=10)):
            # exact merge
            result = {}
            used_carbs = set()

            # 1) точные совпадения ключей
            for ts, ins in ins_by_ts.items():
                if ts in carbs_by_ts:
                    result[ts] = {"insulin": ins, "carb": carbs_by_ts[ts]}
                    used_carbs.add(ts)

            # Подготовим списки для ближайшего совпадения
            remaining_ins = {ts: v for ts, v in ins_by_ts.items() if ts not in result}
            remaining_carbs = {ts: v for ts, v in carbs_by_ts.items() if ts not in used_carbs}

            if remaining_ins and remaining_carbs:
                carb_items = list(remaining_carbs.items())
                # 2) ближайшее по модулю разницы времени
                for its, ival in remaining_ins.items():
                    dt_i = _parse_iso(its)
                    if not dt_i:
                        continue
                    best_ts = None
                    best_diff = None
                    for cts, cval in carb_items:
                        if cts in used_carbs:
                            continue
                        dt_c = _parse_iso(cts)
                        if not dt_c:
                            continue
                        diff = abs(dt_i - dt_c)
                        if diff <= window and (best_diff is None or diff < best_diff):
                            best_diff = diff
                            best_ts = cts
                    if best_ts is not None:
                        result[its] = {"insulin": ival, "carb": remaining_carbs[best_ts]}
                        used_carbs.add(best_ts)

            # 3) остатки инсулина без углей — проставим carbs=0
            for ts, ival in ins_by_ts.items():
                if ts not in result:
                    result[ts] = {"insulin": ival, "carb": 0}

            return result

        try:
            printdbg("----- __getBolus(): start -----")
            _preview("raw", raw)

            # 1) Достаём все INSULIN (manual/обычные болюсы тоже идут c activationType='UNDETERMINED')
            insulin_markers = [m for m in raw if isinstance(m, dict) and m.get("type") == "INSULIN"]
            _preview("insulin_markers (type=INSULIN)", insulin_markers)

            # 2) Фильтруем только быстрые болюсы с доставленной дозой
            ins_by_ts = {}
            for m in insulin_markers:
                dv = _deep_get(m, ("data", "dataValues"), {}) or {}
                bolus_type = _get_any(dv, "bolusType")
                delivered = _get_any(dv, "deliveredFastAmount", "deliveredAmount")
                completed = _get_any(dv, "completed", default=True)
                if bolus_type == "FAST" and delivered:
                    try:
                        dose = float(delivered)
                    except Exception:
                        continue
                    if completed is True:  # берём только завершённые
                        ts = m.get("timestamp")
                        if ts:
                            ins_by_ts[ts] = dose
            _preview("ins_by_ts (timestamp->insulin)", ins_by_ts)

            # 3) Ищем углеводы. Источники:
            #   а) маркеры с type='MEAL' (если вдруг есть)
            #   б) явные поля carbs/carbohydrateAmount где угодно внутри маркера
            carb_markers = []
            for m in raw:
                if m.get("type") == "MEAL":
                    carb_markers.append(m)
                    continue
                # пробуем найти carbs глубоко
                dv = _deep_get(m, ("data", "dataValues"), {}) or {}
                carbs = _get_any(dv, "carbs", "carbohydrateAmount", "amount")
                if carbs is not None and m.get("type") != "INSULIN":  # чтобы не ловить случайные из insulin
                    carb_markers.append(m)

            _preview("carb_markers (candidates)", carb_markers)

            carbs_by_ts = {}
            for m in carb_markers:
                ts = m.get("timestamp")
                if not ts:
                    continue
                dv = _deep_get(m, ("data", "dataValues"), {}) or {}
                carbs_val = _get_any(dv, "carbs", "carbohydrateAmount", "amount")
                if carbs_val is None:
                    # иногда угли могут лежать прямым ключом на верхнем уровне
                    carbs_val = m.get("carbs")
                if carbs_val is None:
                    continue
                try:
                    carbs_by_ts[ts] = float(carbs_val)
                except Exception:
                    continue

            _preview("carbs_by_ts (timestamp->carbs)", carbs_by_ts)

            # 4) Сопоставляем инсулин и углеводы: точный ts, иначе ближайший в ±10 минут, иначе carbs=0
            bolus_carbs = _merge_by_time(ins_by_ts, carbs_by_ts)
            _preview("bolus_carbs (merged insulin+carbs)", bolus_carbs)

            # 5) Готовим записи для Nightscout (используем существующую логику)
            entries = self.__getMealEntries(bolus_carbs, tz)
            _preview("entries (final for NS)", entries)

            printdbg("----- __getBolus(): done -----")
            return entries

        except Exception as e:
            printdbg(f"__getBolus(): ERROR: {e!r}")
            raise

    def __getAutoBolus(self, raw, tz):
        insulin=self.__get_treatments(raw, "type", "INSULIN")
        autocorr=self.__get_treatments(insulin, "activationType", "AUTOCORRECTION")
        return self.__getAutoBolusEntries(autocorr, tz)

    def __getBasal(self, raw, tz):
        basal=self.__get_treatments(raw, "type", "AUTO_BASAL_DELIVERY")
        return self.__getBasalEntries(basal, tz)

    def __getSGS(self, raw, tz):
        sgs=self.__get_treatments(raw, "sensorState", "NO_ERROR_MESSAGE")
        return self.__getSGSEntries(sgs, tz)

    def __getBasalEntries(self, raw, tz):
        result = list()
        for basal in raw:
            _,date_string=self.__getDataStringFromIso(basal["timestamp"], tz)
            result.append(dict(
                enteredBy=NS_USER_AGENT,
                eventType="Temp Basal",
                duration=5,
                absolute=basal["data"]["dataValues"]["bolusAmount"],
                created_at=date_string,
                ))
        return result

    def __getAutoBolusEntries(self, raw, tz):
        result = list()
        for corr in raw:
            date, date_string=self.__getDataStringFromIso(corr["timestamp"], tz)
            result.append(dict(
                device=NS_USER_AGENT,
                timestamp=date,
                enteredBy=NS_USER_AGENT,
                created_at=date_string,
                eventType="Correction Bolus",
                insulin=corr["data"]["dataValues"]["deliveredFastAmount"],
                ))
        return result

    def __getMealEntries(self, meals, tz):
        result = list()
        for time, info in meals.items():
            date, date_string=self.__getDataStringFromIso(time, tz)
            result.append(dict(
                timestamp=date,
                enteredBy=NS_USER_AGENT,
                created_at=date_string,
                eventType="Meal",
                glucoseType="sensor",
                carbs=info["carb"],
                insulin=info["insulin"],
                ))
        return result

    def __ns_trend(self, present, past):
        if present["sg"] == 0 or past["sg"] == 0:
            return "null", "null"
        delta = present["sg"] - past["sg"]
        if delta == 0:
            trend = "Flat"
        elif delta < -30:
            trend = "TripleDown"
        elif delta < -15:
            trend = "DoubleDown"
        elif delta < -5:
            trend = "SingleDown"
        elif delta < 0:
            trend = "FortyFiveDown"
        elif delta > 30:
            trend = "TripleUp"
        elif delta > 15:
            trend = "DoubleUp"
        elif delta > 5:
            trend = "SingleUp"
        elif delta > 0:
            trend = "FortyFiveUp"
        else:
            trend = "NOT COMPUTABLE"
        return trend, delta

    def __getDeviceStatus(self, rawdata):
        return [dict(
            device=rawdata["medicalDeviceInformation"]["modelNumber"],
            pump=dict(
                battery=dict(
                    status=rawdata["conduitBatteryStatus"],
                    voltage=rawdata["conduitBatteryLevel"]),
                reservoir=rawdata["activeInsulin"]["amount"],
                status=dict(
                    status=rawdata["systemStatusMessage"],
                    suspended=rawdata["pumpSuspended"])))]

    def __getSGSEntries(self, sgs, tz):
        result = list()
        trend, delta="null", "null"
        for count, sg in enumerate(sgs):
            try:
                trend, delta = self.__ns_trend(sgs[count], sgs[count-1])
            except Exception:
                pass
            date, date_string=self.__getDataStringFromIso(sg["timestamp"], tz)
            result.append(dict(
                device=NS_USER_AGENT,
                direction=trend,
                delta=delta,
                type='sgv',
                sgv=float(sg["sg"]),
                date=date,
                dateString=date_string,
                noise=1))
        return result

    async def __slice_recent_data_for_transmission(self, recent_data, tz):
        # Sending device status
        response = await self.__setDeviceStatus(recent_data)
        if response:
            printdbg("sending device status was ok")
        # Sending all SGS
        response = await self.__setSGS(recent_data["sgs"], tz)
        if response:
            printdbg("sending SGS entries was ok")
        # Sending Basal
        response = await self.__setBasal(recent_data["markers"], tz)
        if response:
            printdbg("sending basal was ok")
        # Sending all Bolus
        response = await self.__setBolus(recent_data["markers"], tz)
        if response:
            printdbg("sending meal bolus was ok")
        # Sending all auto Bolus
        response = await self.__setAutoBolus(recent_data["markers"], tz)
        if response:
            printdbg("sending auto bolus was ok")
        # Sending alarms
        response = await self.__setAlarms(recent_data["notificationHistory"], tz)
        if response:
            printdbg("sending alarm notifications was ok")
        # Sending messages
        response = await self.__setMsgs(recent_data["notificationHistory"], tz)
        if response:
            printdbg("sending message notifications was ok")
        # Sending alerts
        response = await self.__setAlerts(recent_data["notificationHistory"], tz)
        if response:
            printdbg("sending alert notifications was ok")

    # Periodic upload to Nightscout
    async def send_recent_data(
        self, recent_data, timezone
    ):
        printdbg("__send_recent_data()")
        await self.__slice_recent_data_for_transmission(recent_data, timezone)

    async def __test_server_connection(self):
        url = f"{self.__nightscout_url}/api/v1/devicestatus.json"
        response = await self.fetch_async(
                        url, headers=self.__common_headers, params={}
                    )
        if response.status_code == 200:
            self.__is_reachable = True

    # verify connection
    async def reachServer(self):
        """perform reach server check"""
        if not self.__is_reachable:
            await self.__test_server_connection()
        return self.__is_reachable

    def run_in_console(self, data):
        """If running this module directly"""
        print("Sending...")
        asyncio.run(self.reachServer())
        if self.__is_reachable:
            asyncio.run(self.send_recent_data(data))

if __name__ == "__main__":
    test_data={
                #fill me
            }
    parser = argparse.ArgumentParser(
        description="Simulate upload process to Nightscout with testdata"
    )
    parser.add_argument("-u", "--url", dest="url", help="Nightscout URL")
    parser.add_argument("-s", "--secret", dest="secret", help="Nightscout API Secret"
    )

    args = parser.parse_args()

    if args.url is None:
        raise ValueError("URL is required")

    if args.secret is None:
        raise ValueError("Secret is required")

    TESTAPI = NightscoutUploader(
        nightscout_url=args.url,
        nightscout_secret=args.secret
    )

    TESTAPI.run_in_console(test_data)
