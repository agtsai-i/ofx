#!/usr/bin/python
import time, os, httplib, urllib2, uuid
import sys

join = str.join

sites = {
       "amex": {
                 "caps": [ "SIGNON", "CCSTMT" ],
                  "fid": "3101",
                "fiorg": "AMEX",
                  "url": "https://www99.americanexpress.com/myca/ofxdl/us/download?request_type=nl_desktopdownload",
               },
      "chase": {
                 "caps": [ "SIGNON", "CCSTMT" ],
                "fiorg": "B1",
                  "fid": "10898",
                  "url": "https://ofx.chase.com",
                  "clientuid": "INSERT CLIENT UID HERE"
               },
   "fidelity": {
                 "caps": [ "SIGNON", "INVSTMT" ],
                "fiorg": "fidelity.com",
                  "fid": "7776",
                  "url": "https://ofx.fidelity.com/ftgw/OFX/clients/download",
               },
   "vanguard": {
                 "caps": [ "SIGNON", "INVSTMT" ],
                "fiorg": "vanguard.com",
                  "url": "https://vesnc.vanguard.com/us/OfxDirectConnectServlet",
               },
       "usaa": {
                 "caps": [ "SIGNON", "BASTMT" ],
                  "fid": "24591",     # ^- this is what i added, for checking/savings/debit accounts- think "bank statement"
                "fiorg": "USAA", 
                  "url": "https://service2.usaa.com/ofx/OFXServlet",
               "bankid": "314074269", # bank routing #
               }
   }
                                                
def _field(tag,value):
    return "<"+tag+">"+value

def _tag(tag,*contents):
    return join("\r\n",["<"+tag+">"]+list(contents)+["</"+tag+">"])

def _date():
    return time.strftime("%Y%m%d%H%M%S",time.localtime())

def _genuuid():
    return uuid.uuid4().hex

class OFXClient:
    """Encapsulate an ofx client, config is a dict containg configuration"""
    def __init__(self, config, user, password):
        self.password = password
        self.user = user
        self.config = config
        self.cookie = 3
        config["user"] = user
        config["password"] = password
        if not config.has_key("appid"):
            config["appid"] = "QWIN"
            config["appver"] = "1800"

    def _cookie(self):
        self.cookie += 1
        return str(self.cookie)

    """Generate signon message"""
    def _signOn(self):
        config = self.config
        fidata = [ _field("ORG",config["fiorg"]) ]
        if config.has_key("fid"):
            fidata += [ _field("FID",config["fid"]) ]
        return _tag("SIGNONMSGSRQV1",
                    _tag("SONRQ",
                         _field("DTCLIENT",_date()),
                         _field("USERID",config["user"]),
                         _field("USERPASS",config["password"]),
                         _field("LANGUAGE","ENG"),
                         _tag("FI", *fidata),
                         _field("APPID",config["appid"]),
                         _field("APPVER",config["appver"]),
                         _field("CLIENTUID",config["clientuid"]),
                         ))

    def _acctreq(self, dtstart):
        req = _tag("ACCTINFORQ",_field("DTACCTUP",dtstart))
        return self._message("SIGNUP","ACCTINFO",req)

# this is from _ccreq below and reading page 176 of the latest OFX doc.
    def _bareq(self, acctid, dtstart, accttype):
        config=self.config
        req = _tag("STMTRQ",
               _tag("BANKACCTFROM",
                   _field("BANKID",sites [argv[1]] ["bankid"]),
                    _field("ACCTID",acctid),
                _field("ACCTTYPE",accttype)),
               _tag("INCTRAN",
                   _field("DTSTART",dtstart),
                _field("INCLUDE","Y")))
        return self._message("BANK","STMT",req)
    
    def _ccreq(self, acctid, dtstart):
        config=self.config
        req = _tag("CCSTMTRQ",
                   _tag("CCACCTFROM",_field("ACCTID",acctid)),
                   _tag("INCTRAN",
                        _field("DTSTART",dtstart),
                        _field("INCLUDE","Y")))
        return self._message("CREDITCARD","CCSTMT",req)

    def _invstreq(self, brokerid, acctid, dtstart):
        dtnow = time.strftime("%Y%m%d%H%M%S",time.localtime())
        req = _tag("INVSTMTRQ",
                   _tag("INVACCTFROM",
                      _field("BROKERID", brokerid),
                      _field("ACCTID",acctid)),
                   _tag("INCTRAN",
                        _field("DTSTART",dtstart),
                        _field("INCLUDE","Y")),
                   _field("INCOO","Y"),
                   _tag("INCPOS",
                        _field("DTASOF", dtnow),
                        _field("INCLUDE","Y")),
                   _field("INCBAL","Y"))
        return self._message("INVSTMT","INVSTMT",req)

    def _message(self,msgType,trnType,request):
        config = self.config
        return _tag(msgType+"MSGSRQV1",
                    _tag(trnType+"TRNRQ",
                         _field("TRNUID",_genuuid()),
                         _field("CLTCOOKIE",self._cookie()),
                         request))
    
    def _header(self):
        return join("\r\n",[ "OFXHEADER:100",
                           "DATA:OFXSGML",
                           "VERSION:102",
                           "SECURITY:NONE",
                           "ENCODING:USASCII",
                           "CHARSET:1252",
                           "COMPRESSION:NONE",
                           "OLDFILEUID:NONE",
                           "NEWFILEUID:"+_genuuid(),
                           ""])

    def baQuery(self, acctid, dtstart, accttype):
        """Bank account statement request"""
        return join("\r\n",[self._header(),
                       _tag("OFX",
                                self._signOn(),
                                self._bareq(acctid, dtstart, accttype))])
                        
    def ccQuery(self, acctid, dtstart):
        """CC Statement request"""
        return join("\r\n",[self._header(),
                          _tag("OFX",
                               self._signOn(),
                               self._ccreq(acctid, dtstart))])

    def acctQuery(self,dtstart):
        return join("\r\n",[self._header(),
                          _tag("OFX",
                               self._signOn(),
                               self._acctreq(dtstart))])

    def invstQuery(self, brokerid, acctid, dtstart):
        return join("\r\n",[self._header(),
                          _tag("OFX",
                               self._signOn(),
                               self._invstreq(brokerid, acctid,dtstart))])

    def doQuery(self,query,name):
        # N.B. urllib doesn't honor user Content-type, use urllib2
        garbage, path = urllib2.splittype(self.config["url"])
        host, selector = urllib2.splithost(path)
        h = httplib.HTTPSConnection(host)
        h.request('POST', selector, query, 
                  { "Content-type": "application/x-ofx",
                    "Accept": "*/*, application/x-ofx"
                  })
        if 1:
            res = h.getresponse()
            response = res.read()
            res.close()
            
            f = file(name,"w")
            f.write(response)
            f.close()
        else:
            print h
            print self.config["url"], query

        # ...

import getpass
argv = sys.argv
if __name__=="__main__":
    dtstart = time.strftime("%Y%m%d",time.localtime(time.time()-31*86400))
    dtnow = time.strftime("%Y%m%d%H%M%S",time.localtime())
    if len(argv) < 3:
        print "Usage:",sys.argv[0], "site user [account] [CHECKING/SAVINGS/.. if using BASTMT]"
        print "available sites:",join(", ",sites.keys())
        sys.exit()
    passwd = getpass.getpass()
    client = OFXClient(sites[argv[1]], argv[2], passwd)
    if len(argv) < 4:
       query = client.acctQuery("19700101000000")
       client.doQuery(query, argv[1]+"_acct.ofx") 
    else:
       if "CCSTMT" in sites[argv[1]]["caps"]:
          query = client.ccQuery(sys.argv[3], dtstart)
       elif "INVSTMT" in sites[argv[1]]["caps"]:
          query = client.invstQuery(sites[argv[1]]["fiorg"], sys.argv[3], dtstart)
       elif "BASTMT" in sites[argv[1]]["caps"]:
          query = client.baQuery(sys.argv[3], dtstart, sys.argv[4])
       client.doQuery(query, argv[1]+dtnow+".ofx")

