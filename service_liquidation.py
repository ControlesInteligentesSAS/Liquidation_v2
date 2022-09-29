import json
import os
from datetime import datetime, time
from datetime import timedelta, date

from prodict import Prodict


import logging
from logging.handlers import TimedRotatingFileHandler
directorio = os.path.dirname(os.path.realpath(__file__))+"/Logs/"

try:	os.stat(directorio)
except:	os.mkdir(directorio)

logging.basicConfig(
	level		= logging.INFO,
	format		= "%(asctime)s [%(levelname)s]	%(module)s:%(lineno)d:	%(message)s" ,
	datefmt		= '%Y-%m-%d %H:%M:%S',
	handlers	= [TimedRotatingFileHandler(directorio+"/logs.log",when	= 'd',interval	= 1, backupCount	= 3),logging.StreamHandler()]
)

class liquidacion:
    JS              = None
    nombretarifa    = ""
    parambase       = None
    paramzona       = None
    paramVehiculo   = None
    prueba          = False
    detalle         = {}
    conveniossaldo0 = True

    def __init__(self, tarifaspath, tarifa):
        self.tarifa = tarifa
        with open(tarifaspath, 'rb') as f:
            self.JS = json.load(f)

    def calcular(self, di:datetime, df:datetime, usuario, zona, tv, convenios, cardStatus='0', horaPago=''):
        valort          = 0
        self.detalle    = {}

        if cardStatus == '1' and (datetime.now() - datetime.strptime(horaPago, '%Y-%m-%d %H:%M:%S')) < timedelta(minutes = self.JS['tarifas'][0]['tiempo_gracia']):
            fechasalida     = datetime.timestamp(datetime.strptime(horaPago, '%Y-%m-%d %H:%M:%S'))
            now             = datetime.timestamp(datetime.now())
            minSincePay     = (now-fechasalida)/60
            mintoExit       = int(self.JS['tarifas'][0]['tiempo_gracia']-minSincePay)
            self.detalle['MinToExit'] = mintoExit
        
        else:
            tarifa  = self.gettarifa(self.tarifa)
            
            if tarifa is None:
                logging.info("No se encontro tarifa")
                return

            lf  = self.intervalos(tarifa, di,df, usuario, zona, tv)
            lf  = self.agruparcalculos(lf)

            logging.info(lf)

            dcalculo        = None
            valort          = 0
            formulaconvenio = None

            for formula in lf.keys():
                dcalculo    = tarifa["formulas"][formula]
                dias        = lf[formula]

                if dcalculo is not None:
                    alcance = self.dictvalue(dcalculo, "alcance", "transaccion")
                    minutos = 0
                    if alcance == "transaccion":
                        for dia in dias.keys():
                            minutos = minutos + dias[dia]
                        dias        = {}
                        dias[dia]   = minutos

                    for dia in dias.keys():
                        minutos = dias[dia]
                        logging.info("Dia:" + str(dia) + " mins:" + str(minutos))
                        valor   = self.calculoformula(dcalculo, zona, tv, minutos)
                        if valor > 0: formulaconvenio=dcalculo

                        valort  = valort + valor
                        datos   = {'Tarifa':formula, 'minFacturados':dias[dia], 'Total':valor}
                        self.detalle['detailLiquidate'] = datos

            #descuenta convenios
            lconveniosmin, conveniosmins, lconveniosdinero, conveniosdinero = self.getconvenios(tarifa, convenios)

            if formulaconvenio is not None:
                logging.info(" Convenios:" + convenios.__str__())
                valor = self.calculoformula(formulaconvenio, zona, tv,conveniosmins )
                if valort > 0:
                    if self.conveniossaldo0:
                        convenios_minutos = {'Convenio': formula, 'Total': valor*-1}
                        self.detalle['Convenios_Minutos'] = convenios_minutos

                valort = valort - valor
                if valort < 0: valort = 0

            #descuento convenios dinero
            if valort > 0:
                if self.conveniossaldo0:
                    convenios_dinero = {'Convenio': formula, 'Total': valor*-1}
                    self.detalle['Convenios_Dinero'] = convenios_dinero

            valort = valort - conveniosdinero
            if valort < 0: valort = 0


            logging.info("Valor liquidacion $" + str(valort))

        return valort

    def intervalos(self,tarifa, di:datetime, df:datetime, usuario, zona, tv):
        td   = df - di
        dias = td.days

        if td > timedelta(days=dias):
            dias = dias + 1

        lf      = []
        td      = None
        te      = None
        thoy    = di

        if df.date() == di.date():
            # Entro y salio mismo dia

            #formulasdia=self.formulasdia(tarifa, self.diasemana(df),zona)
            formulasdia = self.getformulavalida(tarifa, self.diasemana(df), usuario, zona, tv)
            ld          = []

            for hobj in formulasdia:
                td  = time.fromisoformat(hobj[1])
                td  = thoy.replace(hour=td.hour,minute=td.minute, second=td.second)
                te  = time.fromisoformat(hobj[2])
                te  = thoy.replace(hour=te.hour,minute=te.minute, second=te.second)
                
                ld.append((td.isoformat(),0,hobj[0]))
                ld.append((te.isoformat(),1,hobj[0]))
            
            ld.append((di.isoformat(),2,""))
            ld.append((df.isoformat(),3,""))
            ld.sort(key = lambda x: x[0])

            adentro = False
            formula = ""
            lasttd:time

            for item in ld:
                if adentro and lasttd != item[0]:
                    delta=datetime.fromisoformat(item[0])-datetime.fromisoformat(lasttd)
                    if delta.seconds>1:
                        if item[1] == 0:  lf.append((lasttd, item[0], ""))
                        if item[1] == 3:  lf.append((lasttd,item[0],formula))
                        if item[1] == 1:  lf.append((lasttd, item[0], formula))

                if item[1] == 2:    adentro = True
                if item[1] == 3:    adentro = False
                if item[1] == 0:    formula = item[2]
                if item[1] == 1:    formula = ""
                lasttd = item[0]
            ld.clear()
            return lf
        else:
            fin = False
            while not fin:
                td = thoy.replace(hour=0, minute=0, second=0)
                if di > td: td = di
                te = thoy.replace(hour=23, minute=59, second=59)
                if df < te:
                    te  = df
                    fin = True

                #print(td, te)
                li      = self.intervalos(tarifa,td,te,usuario,zona,tv)
                lf      = lf + li
                thoy    = thoy + timedelta(days=1)
        return lf

    def agruparcalculos(self, lf):
        lfn = {}

        lf.sort(key=lambda x: x[2])
        lastitem    = None
        dias        = {}
        lastformula = None
        lastdia     = ""

        for item in lf:
            if lastformula is not None:
                if lastformula == item[2]:
                    mindia = self.dictvalue(dias, self.getdatestr(item[0]), 0)
                    dias[self.getdatestr(item[0])] = mindia + (datetime.fromisoformat(item[1]) - datetime.fromisoformat(item[0])).seconds / 60
                else:
                    lfn[lastformula]    = dias
                    lastformula         = item[2]
                    dias                = {}
                    dias[self.getdatestr(item[0])] = (datetime.fromisoformat(item[1]) - datetime.fromisoformat(item[0])).seconds / 60
            else:
                lastformula = item[2]
                dias        = {}
                dias[self.getdatestr(item[0])] = (datetime.fromisoformat(item[1]) - datetime.fromisoformat(item[0])).seconds / 60

        if item[2] == lastformula:
            lfn[lastformula] = dias
        
        del lf
        return lfn

    def calculoformula(self, dcalculo, zona, tv, minutos):
        valort = 0

        if dcalculo is not None:
            dvalores = dcalculo["valores"]
            
            for dvalor in dvalores:
                #logging.info("Mins por calcular: " + str(minutos))
                if minutos > 0:
                    minutos, valorintervalo = self.calcularvalor(dvalor, minutos)
                    valort = valort + valorintervalo
            
            while minutos > 0:
                #logging.info("Mins por calcular:" + str(minutos))
                minutos, valorintervalo=self.calcularvalor(dvalor, minutos)
                valort = valort + valorintervalo

        return valort

    def calcularvalor(self, obj, minutos):
        valorintervalo = 0
        if minutos <= self.dictvalue(obj, "mingracia", 0):
            logging.info("Dentro de tiempo de gracia.")
            valorintervalo  = 0
            minutos         = 0
        else:
            if obj["min"] == 0:
                valorintervalo  = obj["valor"]
                minutos         = 0
            else:
                if minutos > obj["min"]:
                    valorintervalo  = obj["valor"]
                    minutos         = minutos - obj["min"]
                else:
                    if self.dictvalue(obj, "fraccion", False):
                        valorintervalo  = obj["valor"] / obj["min"] * minutos
                        minutos         = 0
                    else:
                        valorintervalo  = obj["valor"]
                        minutos         = 0

        return minutos, valorintervalo

    def dictvalue(self, dict, key, defaultv):
        if dict is None: return defaultv
        val = dict.get(key)
        if val is None: return defaultv
        else:           return val

    def getformulavalida(self, tarifa, dia, usuario, zona, tv):
        lf      = []
        reglas  = tarifa["reglas"]

        for regla in reglas:
            if zona in regla["zona"] and usuario == regla["usuario"] and tv in regla["vehiculo"]:
                horario=tarifa["horarios"][regla["horario"]]["rango"]
                for rango in horario:
                    if dia in rango["dias"]:
                        lf.append([regla["formula"],rango["horas"]["desde"],rango["horas"]["hasta"]])

        lf.sort()
        return lf

    def estavigente(self, obj):
        esvigente   = True
        vigencia    = self.dictvalue(obj, "vigencia", "")
        
        if vigencia != "":
            dv = datetime.fromisoformat(vigencia)
            if datetime.now() > dv:
                esvigente = False
        return esvigente

    def diasemana(self, date: datetime):
        # Si es festivo retorna 0
        return date.weekday()

    def getdatestr(self, di):
        return date.fromisoformat(di.split("T")[0]).isoformat()

    def gettarifa(self,tarifa):
        # Busca tarifa a usar en jason
        for tobj in self.JS["tarifas"]:
            if tobj["tarifa"] == self.tarifa:
                self.conveniossaldo0=self.dictvalue(tobj,"conveniossaldo0",True)
                return tobj
        return None


    def getconvenios(self, tarifa, convenios):
        # Busca tarifa a usar en jason
        dconvenios              = {}
        jconvenios              = tarifa["convenios"]
        lconveniosmin           = []
        lconveniosdinero        = []
        conveniomin             = -1
        conveniodinero          = -1
        maxmins                 = 0
        maxdinero               = 0
        convenioacumulamin      = 0
        convenioacumuladinero   = 0

        for idconvenio in jconvenios.keys():
            if idconvenio in str(convenios):
                jconvenio = jconvenios[idconvenio]

                if self.estavigente(jconvenio):
                    if self.dictvalue(jconvenio,"tipo","") == "":
                        #No acumulable
                        if jconvenio["tipovalor"] == 0:    #Minutos
                            if jconvenio["valor"] > maxmins:
                                conveniomin = idconvenio
                                maxmins     = jconvenio["valor"]
                        else:
                            if jconvenio["valor"] > maxdinero:
                                conveniodinero  = idconvenio
                                maxdinero       = jconvenio["valor"]

                    else:
                        #acumula
                        if jconvenio["tipovalor"] == 0:    #Minutos
                            lconveniosmin.append(idconvenio)
                            convenioacumulamin += jconvenio["valor"]
                        else:
                            lconveniosdinero.append(idconvenio)
                            convenioacumuladinero += jconvenio["valor"]

                if convenioacumulamin < maxmins:    lconveniosmin = [conveniomin]
                else:                               maxmin=convenioacumulamin

                if convenioacumuladinero< maxdinero:    lconveniosdinero    = [conveniomin]
                else:                                   maxdinero           = convenioacumuladinero

        return lconveniosmin, maxmins, lconveniosdinero,  maxdinero


def MainApp():
    liq			= liquidacion("/CI24/Logic/json/settings/OviedoNuevo.json", "Oviedo")
    dt_entrada  = datetime.fromisoformat('2022-08-17 10:23:07')
    dt_salida1	= datetime.fromisoformat('2022-08-17 11:16:58')
    zona        = 1
    tv          = 2

    print ("$" + str(liq.calcular(dt_entrada, dt_salida1, "visitante", zona, tv, ["10","11","12"])))
    print (liq.detalle)

if __name__ == '__main__':
    MainApp()

