Attribute VB_Name = "basHelper"
'/*
' * Copyright 2004 Anite - Central Government Division
' *    http://www.anite.com/publicsector
' *
' * Licensed under the Apache License, Version 2.0 (the "License");
' * you may not use this file except in compliance with the License.
' * You may obtain a copy of the License at
' *
' *    http://www.apache.org/licenses/LICENSE-2.0
' *
' * Unless required by applicable law or agreed to in writing, software
' * distributed under the License is distributed on an "AS IS" BASIS,
' * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
' * See the License for the specific language governing permissions and
' * limitations under the License.
' */
Option Explicit
Private Declare Function CoCreateGUID Lib "ole32.dll" Alias _
    "CoCreateGuid" (ByRef pguid _
    As tGUID) As Long

Private Declare Function StringFromGUID2 Lib "ole32.dll" ( _
    ByRef rguid As tGUID, _
    ByVal lpsz As Long, _
    ByVal cbMax As Long _
    ) As Long
    
Private Type tGUID
    Data1 As Long
    Data2 As Integer
    Data3 As Integer
    Data4(7) As Byte
End Type
Private Type tXYPoint
    X As Single
    Y As Single
End Type

Private Type tSide
    s1 As tXYPoint
    s2 As tXYPoint
End Type

'/ standard error message function
Public Function StdErrMsg(ByVal TheError As ErrObject, ByVal TheModule As String, ByVal TheSource As String) As VbMsgBoxResult
    Dim strMsg As String
    strMsg = "The following unexpected error has occurred:" & vbCrLf & vbCrLf
    strMsg = strMsg & "Module: " & TheModule & vbCrLf
    strMsg = strMsg & "Source: " & TheSource & vbCrLf
    strMsg = strMsg & "Error: [" & Err.Number & "] " & Err.Description & " / " & Err.Source & vbCrLf & vbCrLf
    strMsg = strMsg & "What should the application do next?"
    StdErrMsg = MsgBox(strMsg, vbAbortRetryIgnore Or vbDefaultButton2)

End Function

'/ standard error raise function
Public Sub ErrRaise(ByVal TheError As ErrObject, ByVal TheModule As String, ByVal TheSource As String)
    Dim strMsg As String
    strMsg = "Module: " & TheModule & vbCrLf
    strMsg = strMsg & "Source: " & TheSource & vbCrLf
    strMsg = strMsg & "Error: [" & Err.Number & "] " & Err.Description & " / " & Err.Source & vbCrLf & vbCrLf
    Err.Raise Err.Number, TheModule & "." & TheSource, strMsg
End Sub

'/ creates a GUID using MS API
Public Function CreateGUID() As String
    Dim udtGUID As tGUID
    Dim strGUID As String
    strGUID = String$(39, 0)
    If Not CoCreateGUID(udtGUID) Then
        StringFromGUID2 udtGUID, StrPtr(strGUID), 39&
        CreateGUID = Left$(strGUID, 38)
    End If
End Function

Public Function ValidatePath(Path As String) As String
    If Not (Right$(Path, 1) = "\") Then
        ValidatePath = Path & "\"
    Else
        ValidatePath = Path
    End If
End Function

Public Function IntersectBox(Left As Single, Top As Single, Width As Single, Height As Single, X As Single, Y As Single, ByRef IntersectX As Single, ByRef IntersectY As Single) As Boolean
    
    Dim CenterX As Single
    Dim CenterY As Single
    
    CenterX = Left + (Width / 2)
    CenterY = Top + (Height / 2)
    IntersectBox = IntersectBoxLine(Left, Top, Width, Height, X, Y, CenterX, CenterY, IntersectX, IntersectY)
End Function

Public Function IntersectBoxLine(Left As Single, Top As Single, Width As Single, Height As Single, X1 As Single, Y1 As Single, X2 As Single, Y2 As Single, ByRef IntersectX As Single, ByRef IntersectY As Single) As Boolean
    Dim Right As Single
    Dim Bottom As Single
    
    Right = Left + Width
    Bottom = Top + Height
    
    Dim Sides(3) As tSide
    Sides(0).s1.X = Left
    Sides(0).s1.Y = Top
    Sides(0).s2.X = Right
    Sides(0).s2.Y = Top
    
    Sides(1).s1.X = Right
    Sides(1).s1.Y = Top
    Sides(1).s2.X = Right
    Sides(1).s2.Y = Bottom
    
    Sides(2).s1.X = Left
    Sides(2).s1.Y = Bottom
    Sides(2).s2.X = Right
    Sides(2).s2.Y = Bottom
    
    Sides(3).s1.X = Left
    Sides(3).s1.Y = Top
    Sides(3).s2.X = Left
    Sides(3).s2.Y = Bottom
    
    '# now have 4 lines
    Dim lngCount As Long
    For lngCount = 0 To 3
        If Lines_Intersect(X2, Y2, X1, Y1, Sides(lngCount).s1.X, Sides(lngCount).s1.Y, Sides(lngCount).s2.X, Sides(lngCount).s2.Y, IntersectX, IntersectY) Then
'            Debug.Print "Intersect at", lngCount
            Exit For
        End If
    Next
    If lngCount > 3 Then
        IntersectBoxLine = False
        Debug.Print "Could Not Intersect"
    Else
        IntersectBoxLine = True
    End If
End Function



'/ returns true if the two lines intersect. IntersectX and Y contain the intersection point if one exists
Private Function Lines_Intersect(Ax As Single, Ay As Single, Bx As Single, By As Single, CX As Single, CY As Single, Dx As Single, Dy As Single, IntersectionX As Single, IntersectionY As Single) As Boolean
   '# I have little idea of how this routine works - I pinched and modified is slightly from something on the net
   '# if you dont understand the maths involved - DONT TOUCH THIS ROUTINE
    Dim Rn As Single
    Dim Rd As Single
    Dim Sn As Single
    Dim Intersection_AB As Single
    Dim Intersection_CD As Single
'    Debug.Print Ax, Ay, Bx, By, Cx, Cy, Dx, Dy
    Rn = (Ay - CY) * (Dx - CX) - (Ax - CX) * (Dy - CY)
    Rd = (Bx - Ax) * (Dy - CY) - (By - Ay) * (Dx - CX)

    If Rd = 0 Then
        
'        ; Lines are parralel.
'
'        ; If Rn# is also 0 then lines are coincident.  All points intersect.
'        ; Otherwise, there is no intersection point.
'
        Lines_Intersect = False
    
    Else
    
        '; The lines intersect at some point.  Calculate the intersection point.
        '# note: the lines MAY intersect at some point (if infinite in length I think)
        Sn = (Ay - CY) * (Bx - Ax) - (Ax - CX) * (By - Ay)

        '# note: this bit copes with the finite length of the lines (I think)
        Intersection_AB = Rn / Rd
        Intersection_CD = Sn / Rd
        If Intersection_AB < 0 Or Intersection_AB > 1 Or Intersection_CD < 0 Or Intersection_CD > 1 Then
            '# the lines do not intersect
            Lines_Intersect = False
            Exit Function
        End If

        IntersectionX = Ax + Intersection_AB * (Bx - Ax)
        IntersectionY = Ay + Intersection_AB * (By - Ay)
            
        Lines_Intersect = True
        
    End If


End Function


