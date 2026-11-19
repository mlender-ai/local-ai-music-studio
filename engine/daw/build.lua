-- Local, single-job ReaScript. The Python controller launches this in an isolated
-- host. Open a fresh tab so existing music and user projects stay untouched.
local r = reaper
local dir = assert(({r.get_action_context()})[2]:match("^(.*[/\\])"))
local function exists(path)
  local f = io.open(path,"rb")
  if f then f:close(); return true end
end
local function fx(track, name)
  local id = r.TrackFX_AddByName(track, name, false, -1)
  assert(id >= 0 and r.TrackFX_GetEnabled(track,id), "Unavailable FX: "..name)
  return id
end
local function parameter(track,id,index,value)
  assert(r.TrackFX_SetParamNormalized(track,id,index,value), "RS5K parameter "..index)
end
local function dbparam(track,id,index,db)
  local lo,hi = 0,1
  for _=1,22 do
    local ok,s = r.TrackFX_FormatParamValueNormalized(track,id,index,(lo+hi)/2)
    assert(ok,"Cannot inspect parameter units")
    local value = tonumber(s:match("[-+]?[%d%.]+")) or -150
    if value < db then lo=(lo+hi)/2 else hi=(lo+hi)/2 end
  end
  parameter(track,id,index,(lo+hi)/2)
end
local function build()
  assert(not exists(dir.."Studio.RPP"),"Studio.RPP already exists")
  local cfg = {}
  for line in io.lines(dir.."mix.tsv") do
    local k,v = line:match("^([%w_]+)\t([%d%.%-]+)$")
    cfg[assert(k)] = assert(tonumber(v))
  end
  r.Main_OnCommand(40859,0) -- New project tab
  r.Main_openProject(dir.."Score.RPP")
  local proj, path = r.EnumProjects(-1,"")
  assert(path==dir.."Score.RPP","Wrong active project")
  local tracks={}
  for i=0,r.CountTracks(proj)-1 do
    local t=r.GetTrack(proj,i)
    local _,name=r.GetTrackName(t)
    tracks[name]=t
    assert(r.TrackFX_GetCount(t)==0 and r.CountTrackMediaItems(t)==14,"Unexpected score layout")
  end
  local zone_count=0
  for line in io.lines(dir.."zones.tsv") do
    local lane,key,ch,file,pitch,db=line:match("^(%w+)\t(%d+)\t(%d+)\t([a-f0-9]+%.%w+)\t([%d%.%-]+)\t([%d%.%-]+)$")
    local track=assert(tracks[lane],"Invalid sampler lane")
    local sample=dir.."Samples/"..file
    assert(exists(sample),"Missing sample "..sample)
    local id=fx(track,"ReaSamplOmatic5000")
    assert(r.TrackFX_SetNamedConfigParm(track,id,"FILE0",sample))
    assert(r.TrackFX_SetNamedConfigParm(track,id,"DONE",""))
    local ok,loaded=r.TrackFX_GetNamedConfigParm(track,id,"FILE0")
    assert(ok and loaded:match("[^/\\]+$")==file,"Sample loading failed")
    parameter(track,id,2,0) -- velocity controls amplitude
    parameter(track,id,3,key/127)
    parameter(track,id,4,key/127)
    parameter(track,id,5,0.5)
    parameter(track,id,6,0.5)
    parameter(track,id,7,ch/16)
    parameter(track,id,11,1) -- obey note-offs
    parameter(track,id,15,0.5+pitch/160)
    if tonumber(db) ~= 0 then dbparam(track,id,0,tonumber(db)) end
    zone_count=zone_count+1
  end
  local function bus(name)
    local n=r.CountTracks(proj)
    r.InsertTrackAtIndex(n,true)
    local t=r.GetTrack(proj,n)
    r.GetSetMediaTrackInfo_String(t,"P_NAME",name,true)
    return t
  end
  local function send(t,target,gain)
    local send_id=r.CreateTrackSend(t,target)
    assert(send_id>=0)
    r.SetTrackSendInfo_Value(t,0,send_id,"D_VOL",gain)
    r.SetTrackSendInfo_Value(t,0,send_id,"I_MIDIFLAGS",31) -- audio only
  end
  local drum_bus=bus("Drum Bus")
  for _,name in ipairs({"kick","snare","hat","openhat"}) do
    r.SetMediaTrackInfo_Value(tracks[name],"B_MAINSEND",0)
    send(tracks[name],drum_bus,1)
  end
  local room=bus("Room")
  local rv=fx(room,"ReaVerbate")
  dbparam(room,rv,0,0) -- wet
  parameter(room,rv,1,0) -- dry
  send(drum_bus,room,cfg.drums_send)
  send(tracks.keys,room,cfg.keys_send)
  send(tracks.guitar,room,cfg.guitar_send)
  for name,t in pairs(tracks) do
    r.SetMediaTrackInfo_Value(t,"D_VOL",cfg[name])
    r.SetMediaTrackInfo_Value(t,"D_PAN",cfg[name.."_pan"])
  end
  local eq=fx(tracks.keys,"ReaEQ")
  assert(r.TrackFX_SetEQParam(tracks.keys,eq,2,0,0,360,false))
  -- ReaEQ gain in linear amplitude
  assert(r.TrackFX_SetEQParam(tracks.keys,eq,2,0,1,10^(cfg.keys_bell_db/20),false))
  -- Write a short room-return fade at the end; preserve dry note attacks.
  local env=assert(r.GetFXEnvelope(room,rv,0,true),"Room wet envelope unavailable")
  if env then
    local mode=r.GetEnvelopeScalingMode(env)
    for _,p in ipairs({{0,1},{cfg.duration-0.5,1},{cfg.duration,0}}) do
      r.InsertEnvelopePoint(env,p[1],r.ScaleToEnvelopeMode(mode,p[2]*r.TrackFX_GetParamNormalized(room,rv,0)),0,0,false,true)
    end
    r.Envelope_SortPoints(env)
  end
  r.GetSetProjectInfo(proj,"RENDER_BOUNDSFLAG",0,true)
  r.GetSetProjectInfo(proj,"RENDER_STARTPOS",0,true)
  r.GetSetProjectInfo(proj,"RENDER_ENDPOS",cfg.duration,true)
  r.GetSetProjectInfo(proj,"RENDER_TAILFLAG",0,true)
  r.GetSetProjectInfo(proj,"RENDER_SRATE",48000,true)
  r.GetSetProjectInfo(proj,"RENDER_CHANNELS",2,true)
  r.GetSetProjectInfo_String(proj,"RENDER_FORMAT","ZXZhdxgAAA==",true) -- PCM WAV 24
  r.GetSetProjectInfo_String(proj,"RENDER_FILE",dir,true)
  r.GetSetProjectInfo_String(proj,"RENDER_PATTERN","reaper-mixed",true)
  r.Main_SaveProjectEx(proj,dir.."Studio.RPP",8)
  assert(exists(dir.."Studio.RPP"),"Save failed")
  return "BUILT\n"..r.GetAppVersion().."\n"..zone_count.." sampler zones\n"
end
local ok,msg=pcall(build)
local report=assert(io.open(dir.."host-status.tmp","w"))
report:write(ok and msg or "ERROR\n"..tostring(msg))
report:close()
assert(os.rename(dir.."host-status.tmp", dir.."host-status.txt"))
