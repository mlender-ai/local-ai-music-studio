-- Shared stock FX operations, using values displayed by the running host.
local r = reaper
local function amp(db) return 10^(db/20) end
local function fx(track, name)
  local index = r.TrackFX_AddByName(track, name, false, -1)
  assert(index >= 0 and r.TrackFX_GetEnabled(track,index) and not r.TrackFX_GetOffline(track,index), name)
  return index
end
local function set(t, i, p, value)
  assert(r.TrackFX_SetParamNormalized(t, i, p, value), "Could not set parameter "..p)
end
local function displayed(t, i, p, target)
  local low, high = 0, 1
  for _=1,24 do
    local mid = (low + high) / 2
    local ok, value = r.TrackFX_FormatParamValueNormalized(t,i,p,mid)
    assert(ok, "Cannot read plugin units")
    local number = tonumber(value:match("[-+]?[%d%.]+")) or -150
    if number < target then low=mid else high=mid end
  end
  set(t,i,p,(low+high)/2)
  return r.TrackFX_GetParamNormalized(t,i,p)
end
local function eq(t,hp,bell,gain,shelf,shelf_db)
  local i=fx(t,"ReaEQ")
  if hp then
    assert(r.TrackFX_SetEQParam(t,i,0,0,0,hp,false))
    assert(r.TrackFX_SetEQBandEnabled(t,i,0,0,true))
  end
  if bell then
    assert(r.TrackFX_SetEQParam(t,i,2,0,0,bell,false))
    assert(r.TrackFX_SetEQParam(t,i,2,0,1,amp(gain),false))
    assert(r.TrackFX_SetEQBandEnabled(t,i,2,0,true))
  end
  if shelf then
    assert(r.TrackFX_SetEQParam(t,i,4,0,0,shelf,false))
    assert(r.TrackFX_SetEQParam(t,i,4,0,1,amp(shelf_db),false))
    assert(r.TrackFX_SetEQBandEnabled(t,i,4,0,true))
  end
end
local function compression(t,threshold,ratio,attack,release)
  local i=fx(t,"ReaComp")
  for p,v in ipairs({threshold,ratio,attack,release}) do displayed(t,i,p-1,v) end
end
local function send(t,b,db)
  local i=r.CreateTrackSend(t,b)
  assert(i>=0,"Cannot create send")
  assert(r.SetTrackSendInfo_Value(t,0,i,"D_VOL",amp(db)))
  assert(r.SetTrackSendInfo_Value(t,0,i,"I_MIDIFLAGS",31))
end
local function room(t,size,damping,predelay,hp,lp)
  local i=fx(t,"ReaVerbate")
  set(t,i,1,0)
  displayed(t,i,0,0)
  for p,value in pairs({[2]=size,[3]=damping,[5]=predelay,[6]=lp,[7]=hp}) do
    displayed(t,i,p,value)
  end
  return i
end
local function automation(t,i,p,points)
  local values={}
  for index,point in ipairs(points) do
    displayed(t,i,p,point[2])
    values[index]=r.TrackFX_GetParam(t,i,p)
  end
  displayed(t,i,p,points[1][2])
  local envelope=assert(r.GetFXEnvelope(t,i,p,true),"Missing FX envelope")
  local mode=r.GetEnvelopeScalingMode(envelope)
  for index,point in ipairs(points) do
    local value=r.ScaleToEnvelopeMode(mode,values[index])
    assert(r.InsertEnvelopePoint(envelope,point[1],value,0,0,false,true))
  end
  r.Envelope_SortPoints(envelope)
end
return {amp=amp, fx=fx, set=set, displayed=displayed, eq=eq, compression=compression, send=send, room=room, automation=automation}
